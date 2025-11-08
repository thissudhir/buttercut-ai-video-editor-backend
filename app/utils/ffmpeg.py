import subprocess
import re
from typing import Optional, List, Tuple
from pathlib import Path
import logging

from app.config import settings
from app.models import Overlay

logger = logging.getLogger(__name__)

class FFmpegHelper:
    """Helper class for FFmpeg operations - Professional video editor quality"""

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
            logger.error(f"Error probing duration: {e}")
            return None

    @staticmethod
    def probe_dimensions(video_path: str) -> Optional[Tuple[int, int]]:
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
            logger.error(f"Error probing dimensions: {e}")
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
    def escape_ffmpeg_text(text: str) -> str:
        """Escape special characters for FFmpeg drawtext filter"""
        # FFmpeg requires escaping: : ' \ [ ]
        return text.replace('\\', '\\\\').replace("'", "'\\''").replace(":", "\\:").replace('[', '\\[').replace(']', '\\]')

    @staticmethod
    def build_filter_complex(
        overlays: List[Overlay],
        video_width: int,
        video_height: int,
        overlay_files: dict = None
    ) -> Tuple[Optional[str], bool, bool, int]:
        """
        Build FFmpeg filter_complex string that exactly matches frontend preview

        Returns: (filter_complex_string, has_image_overlays, has_video_overlays, final_stream_index)
        """
        if overlay_files is None:
            overlay_files = {}

        # Sort overlays by zIndex (ascending) to apply in correct order
        sorted_overlays = sorted(overlays, key=lambda o: o.zIndex or 0)

        filters = []
        has_image_overlays = False
        has_video_overlays = False
        current_stream = "[0:v]"
        input_index = 1  # Track input stream indices for images/videos
        filter_index = 0  # Track the actual filter output stream index (v0, v1, v2, etc.)

        for idx, overlay in enumerate(sorted_overlays):
            # Skip if hidden or locked (though locked should still render)
            if not (overlay.visible if overlay.visible is not None else True):
                continue

            if overlay.type == "text":
                # Build text overlay with all properties
                text = FFmpegHelper.escape_ffmpeg_text(overlay.content)

                # Extract properties with defaults
                x = overlay.x
                y = overlay.y
                logger.info(f"Processing text overlay: '{text[:30]}...' at position ({x}, {y})")
                font_size = overlay.fontSize or 24
                font_color = overlay.fontColor or "white"
                opacity = overlay.opacity if overlay.opacity is not None else 1.0
                rotation = overlay.rotation if overlay.rotation is not None else 0
                scale_factor = overlay.scale if overlay.scale is not None else 1.0
                font_weight = overlay.fontWeight or "normal"
                text_align = overlay.textAlign or "left"

                # Apply scale to font size
                actual_font_size = int(font_size * scale_factor)

                # Build enable expression for timing
                enable = f"between(t,{overlay.start_time},{overlay.end_time})"

                # Convert opacity to alpha (0-1 to 0.0-1.0)
                alpha = f"@{opacity:.2f}"

                # Build filter with proper syntax
                filter_parts = [
                    f"text='{text}'",
                    f"x={x}",
                    f"y={y}",
                    f"fontsize={actual_font_size}",
                    f"fontcolor={font_color}{alpha}",
                ]

                # Add box for better visibility
                filter_parts.extend([
                    "box=1",
                    f"boxcolor=black@{opacity * 0.7:.2f}",  # Box opacity matches text
                    "boxborderw=5",
                ])

                # Add rotation if needed (in radians)
                if rotation != 0:
                
                    pass

                filter_parts.append(f"enable='{enable}'")

                text_filter = f"{current_stream}drawtext={':'.join(filter_parts)}[v{filter_index}]"
                filters.append(text_filter)
                current_stream = f"[v{filter_index}]"

                logger.info(f"Text overlay {filter_index}: pos=({x},{y}), size={actual_font_size}, opacity={opacity}, time={overlay.start_time}-{overlay.end_time}")
                filter_index += 1

            elif overlay.type == "image" and overlay.content in overlay_files:
                has_image_overlays = True

                # Extract properties
                x = overlay.x
                y = overlay.y
                logger.info(f"Processing image overlay at position ({x}, {y})")
                width = overlay.width or 200
                height = overlay.height or 100
                opacity = overlay.opacity if overlay.opacity is not None else 1.0
                rotation = overlay.rotation if overlay.rotation is not None else 0
                scale_factor = overlay.scale if overlay.scale is not None else 1.0

                # Apply scale to dimensions
                actual_width = int(width * scale_factor)
                actual_height = int(height * scale_factor)

                # Build enable expression
                enable = f"between(t,{overlay.start_time},{overlay.end_time})"

                # Scale and prepare image with alpha channel
                scale_filter = f"[{input_index}:v]scale={actual_width}:{actual_height}"

                # Apply opacity if not 1.0
                if opacity < 1.0:
                    scale_filter += f",format=rgba,colorchannelmixer=aa={opacity:.2f}"

                scale_filter += f"[img{filter_index}]"

                # Apply rotation if needed
                if rotation != 0:
                    # Convert degrees to radians
                    rad = rotation * 3.14159 / 180
                    rotation_filter = f"[img{filter_index}]rotate={rad}:c=none[img{filter_index}_rot]"
                    filters.append(scale_filter)
                    filters.append(rotation_filter)
                    overlay_input = f"[img{filter_index}_rot]"
                else:
                    filters.append(scale_filter)
                    overlay_input = f"[img{filter_index}]"

                # Overlay onto video with proper timing
                overlay_filter = f"{current_stream}{overlay_input}overlay={x}:{y}:enable='{enable}'[v{filter_index}]"
                filters.append(overlay_filter)
                current_stream = f"[v{filter_index}]"
                input_index += 1

                logger.info(f"Image overlay {filter_index}: pos=({x},{y}), size={actual_width}x{actual_height}, opacity={opacity}, rotation={rotation}, time={overlay.start_time}-{overlay.end_time}")
                filter_index += 1

            elif overlay.type == "video" and overlay.content in overlay_files:
                has_video_overlays = True

                # Extract properties
                x = overlay.x
                y = overlay.y
                logger.info(f"Processing video overlay at position ({x}, {y})")
                width = overlay.width or 300
                height = overlay.height or 200
                opacity = overlay.opacity if overlay.opacity is not None else 1.0
                rotation = overlay.rotation if overlay.rotation is not None else 0
                scale_factor = overlay.scale if overlay.scale is not None else 1.0
                start_time = overlay.start_time
                end_time = overlay.end_time
                duration = end_time - start_time

                # Apply scale to dimensions
                actual_width = int(width * scale_factor)
                actual_height = int(height * scale_factor)

                # Build video filter chain
                video_filters = f"[{input_index}:v]"

                # Trim to duration (this prevents "shortest" issue!)
                video_filters += f"trim=duration={duration},setpts=PTS-STARTPTS"

                # Scale
                video_filters += f",scale={actual_width}:{actual_height}"

                # Apply opacity if needed
                if opacity < 1.0:
                    video_filters += f",format=rgba,colorchannelmixer=aa={opacity:.2f}"

                # Apply rotation if needed
                if rotation != 0:
                    rad = rotation * 3.14159 / 180
                    video_filters += f",rotate={rad}:c=none"

                video_filters += f"[clip{filter_index}]"
                filters.append(video_filters)

                # Overlay with timing - use enable to show only during start_time to end_time
                enable = f"between(t,{start_time},{end_time})"
                overlay_filter = f"{current_stream}[clip{filter_index}]overlay={x}:{y}:enable='{enable}'[v{filter_index}]"
                filters.append(overlay_filter)
                current_stream = f"[v{filter_index}]"
                input_index += 1

                logger.info(f"Video overlay {filter_index}: pos=({x},{y}), size={actual_width}x{actual_height}, opacity={opacity}, rotation={rotation}, time={start_time}-{end_time}, duration={duration}s")
                filter_index += 1

        if filters:
            # Join all filters with semicolons
            filter_str = ';'.join(filters)
            logger.info(f"Complete filter chain: {filter_str}")
            # Return the index of the last filter (filter_index - 1 since we incremented after creating each filter)
            return filter_str, has_image_overlays, has_video_overlays, filter_index - 1

        return None, False, False, -1

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
        Build complete FFmpeg command that produces output matching frontend preview exactly

        Args:
            input_path: Path to main video file
            output_path: Path for output video
            overlays: List of overlay objects (will be sorted by zIndex)
            video_width: Width of video
            video_height: Height of video
            overlay_files: Dict mapping overlay content names to file paths
        """
        if overlay_files is None:
            overlay_files = {}

        cmd = [settings.FFMPEG_PATH, "-y"]

        # Main video input
        cmd.extend(["-i", input_path])

        # Sort overlays by zIndex to determine input order
        sorted_overlays = sorted(overlays, key=lambda o: o.zIndex or 0)

        # Add image/video overlay files as additional inputs in correct order
        for overlay in sorted_overlays:
            if overlay.type in ["image", "video"] and overlay.content in overlay_files:
                overlay_file_path = overlay_files[overlay.content]
                cmd.extend(["-i", overlay_file_path])
                logger.info(f"Adding input: {overlay.type} from {overlay_file_path}")

        # Build filter complex
        filter_complex, has_images, has_videos, final_stream_index = FFmpegHelper.build_filter_complex(
            overlays, video_width, video_height, overlay_files
        )

        if filter_complex:
            cmd.extend(["-filter_complex", filter_complex])

            # Map output - use the final filtered video stream
            cmd.extend(["-map", f"[v{final_stream_index}]"])

            # Map audio from original video (stream 0)
            cmd.extend(["-map", "0:a?"])

            # Encoding settings - high quality to match preview
            cmd.extend([
                "-c:v", "libx264",
                "-preset", "medium",
                "-crf", "18",  # Higher quality (lower CRF)
                "-pix_fmt", "yuv420p",  # Compatibility
                "-c:a", "aac",  # Re-encode audio for safety
                "-b:a", "192k",
                "-movflags", "+faststart"  # Web optimization
            ])
        else:
            # No overlays, just copy
            cmd.extend(["-c", "copy"])

        cmd.append(output_path)

        logger.info(f"Final FFmpeg command: {' '.join(cmd)}")
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
