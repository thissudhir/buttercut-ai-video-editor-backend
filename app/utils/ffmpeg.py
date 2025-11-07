import subprocess
import re
from typing import Optional, List
from pathlib import Path

from app.config import settings
from app.models import Overlay

class FFmpegHelper:
    """Helper class for FFmpeg operations"""
    
    @staticmethod
    def probe_duration(video_path: str) -> Optional[float]:
        """Get video duration in seconds using ffprobe"""
        try:
            cmd = [
                settings.FFPROBE_PATH,
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=nw=1:nk=1",
                video_path
            ]
            output = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode().strip()
            return float(output)
        except Exception as e:
            print(f"Error probing duration: {e}")
            return None
    
    @staticmethod
    def probe_dimensions(video_path: str) -> Optional[tuple]:
        """Get video width and height"""
        try:
            cmd = [
                settings.FFPROBE_PATH,
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height",
                "-of", "csv=s=x:p=0",
                video_path
            ]
            output = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode().strip()
            w, h = output.split('x')
            return int(w), int(h)
        except Exception as e:
            print(f"Error probing dimensions: {e}")
            return None
    
    @staticmethod
    def parse_time_to_seconds(time_str: str) -> float:
        """Convert HH:MM:SS.ms to seconds"""
        try:
            parts = time_str.split(':')
            if len(parts) != 3:
                return 0.0
            hours, minutes, seconds = parts
            return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
        except Exception:
            return 0.0
    
    @staticmethod
    def build_filter_complex(
        overlays: List[Overlay],
        video_width: int,
        video_height: int,
        overlay_files: dict = None
    ) -> tuple:
        """
        Build FFmpeg filter_complex string for overlays
        Returns: (filter_complex_string, has_image_overlays, has_video_overlays)
        """
        if overlay_files is None:
            overlay_files = {}

        filters = []
        has_image_overlays = False
        has_video_overlays = False
        current_stream = "[0:v]"  
        image_input_index = 1  

        for idx, overlay in enumerate(overlays):
            if overlay.type == "text":
                text = overlay.content.replace("'", "'\\''").replace(":", "\\:")
                enable = f"between(t,{overlay.start_time},{overlay.end_time})"

                # Build drawtext filter with better formatting
                # Round x and y to integers for FFmpeg
                filter_parts = [
                    f"text='{text}'",
                    f"x={int(round(overlay.x))}",
                    f"y={int(round(overlay.y))}",
                    f"fontsize={overlay.font_size}",
                    f"fontcolor={overlay.color}",
                    "box=1",
                    "boxcolor=black@0.5",
                    "boxborderw=5",
                    f"enable='{enable}'"
                ]
                filters.append(f"{current_stream}drawtext={':'.join(filter_parts)}[v{idx}]")
                current_stream = f"[v{idx}]"

            elif overlay.type == "image" and overlay.content in overlay_files:
                has_image_overlays = True
                print(f"DEBUG: Processing image overlay - content: '{overlay.content}', file: '{overlay_files[overlay.content]}'")
                # Image overlay using overlay filter
                enable = f"between(t,{overlay.start_time},{overlay.end_time})"

                # Scale and position image overlay
                # Input stream for image is [image_input_index:v]
                # Round x and y to integers
                filters.append(
                    f"[{image_input_index}:v]scale=200:200[img{idx}];"
                    f"{current_stream}[img{idx}]overlay={int(round(overlay.x))}:{int(round(overlay.y))}:enable='{enable}'[v{idx}]"
                )
                current_stream = f"[v{idx}]"
                image_input_index += 1
            elif overlay.type == "image" and overlay.content not in overlay_files:
                print(f"DEBUG: Image overlay NOT FOUND - content: '{overlay.content}', available files: {list(overlay_files.keys())}")

            elif overlay.type == "video" and overlay.content in overlay_files:
                has_video_overlays = True
                print(f"DEBUG: Processing video overlay - content: '{overlay.content}', file: '{overlay_files[overlay.content]}'")

                # Video clip overlay
                # TEMP DEBUG: Remove enable to test if overlay appears at all
                # Just overlay from the beginning to verify it works
                # Round x and y to integers

                filters.append(
                    f"[{image_input_index}:v]scale=300:200[clip{idx}];"
                    f"{current_stream}[clip{idx}]overlay={int(round(overlay.x))}:{int(round(overlay.y))}:shortest=1[v{idx}]"
                )
                current_stream = f"[v{idx}]"
                image_input_index += 1

                print(f"DEBUG: Video overlay filter created - will appear from start of video at position ({int(round(overlay.x))},{int(round(overlay.y))})")
            elif overlay.type == "video" and overlay.content not in overlay_files:
                print(f"DEBUG: Video overlay NOT FOUND - content: '{overlay.content}', available files: {list(overlay_files.keys())}")

        if filters:
            # Join all filters with semicolons
            filter_str = ';'.join(filters)
            # The final output stream label needs to be removed to map to default output
            # Find the last occurrence of [vX] pattern and remove it
            if current_stream and current_stream != "[0:v]":
                # Remove the final output label so FFmpeg uses it as default output
                filter_str = filter_str.rstrip(current_stream)
            return filter_str, has_image_overlays, has_video_overlays

        return None, False, False
    
    @staticmethod
    def build_command(
        input_path: str,
        output_path: str,
        overlays: List[Overlay],
        video_width: int,
        video_height: int,
        overlay_files: dict = None
    ) -> List[str]:
        """
        Build complete FFmpeg command with support for image/video overlays

        Args:
            input_path: Path to main video file
            output_path: Path for output video
            overlays: List of overlay objects
            video_width: Width of video
            video_height: Height of video
            overlay_files: Dict mapping overlay content names to file paths
        """
        if overlay_files is None:
            overlay_files = {}

        cmd = [settings.FFMPEG_PATH, "-y", "-i", input_path]

        # Add image/video overlay files as additional inputs
        for overlay in overlays:
            if overlay.type in ["image", "video"] and overlay.content in overlay_files:
                overlay_file_path = overlay_files[overlay.content]
                cmd.extend(["-i", overlay_file_path])

        # Build filter complex
        filter_complex, has_images, has_videos = FFmpegHelper.build_filter_complex(
            overlays, video_width, video_height, overlay_files
        )

        if filter_complex:
            cmd.extend(["-filter_complex", filter_complex])
            # Re-encode video with overlays
            cmd.extend([
                "-c:v", "libx264",
                "-preset", "medium",
                "-crf", "23",
                "-c:a", "copy"
            ])
        else:
            # No overlays, just copy
            cmd.extend(["-c", "copy"])

        cmd.append(output_path)
        return cmd
    
    @staticmethod
    def extract_progress_from_line(line: str, duration: Optional[float]) -> Optional[int]:
        """Extract progress percentage from FFmpeg output line"""
        if not duration or "time=" not in line:
            return None
        
        try:
            # Extract time value
            match = re.search(r'time=(\S+)', line)
            if not match:
                return None
            
            time_str = match.group(1)
            current_seconds = FFmpegHelper.parse_time_to_seconds(time_str)
            
            # Calculate percentage
            progress = min(99, int((current_seconds / duration) * 100))
            return progress
        except Exception:
            return None