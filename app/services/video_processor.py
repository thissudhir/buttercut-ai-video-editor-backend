import asyncio
from datetime import datetime
from pathlib import Path
from typing import List
import logging

from app.models import Overlay, JobStatus
from app.config import settings
from app.utils.ffmpeg import FFmpegHelper
from app.services.job_manager import job_manager

logger = logging.getLogger(__name__)

class VideoProcessor:
    """Handles video processing with FFmpeg"""
    
    def __init__(self):
        self.active_jobs = 0
        self.semaphore = asyncio.Semaphore(settings.MAX_CONCURRENT_JOBS)
    
    async def process_video(self, job_id: str, overlays: List[Overlay], overlay_files: dict = None):
        """
        Process video with overlays

        Args:
            job_id: Unique job identifier
            overlays: List of overlay configurations
            overlay_files: Dict mapping overlay content names to file paths
        """
        async with self.semaphore:
            self.active_jobs += 1
            try:
                await self._process_video_impl(job_id, overlays, overlay_files or {})
            finally:
                self.active_jobs -= 1

    async def _process_video_impl(self, job_id: str, overlays: List[Overlay], overlay_files: dict):
        """Internal video processing implementation"""
        job = await job_manager.get_job(job_id)
        if not job:
            logger.error(f"Job {job_id} not found")
            return

        input_path = job['video_path']
        output_path = Path(settings.RESULTS_DIR) / f"{job_id}_output.mp4"

        try:
            # Update status to processing
            await job_manager.update_job(job_id, {
                "status": JobStatus.PROCESSING,
                "message": "Analyzing video..."
            })

            # Probe video properties
            duration = FFmpegHelper.probe_duration(input_path)
            dimensions = FFmpegHelper.probe_dimensions(input_path)

            if not duration or not dimensions:
                raise Exception("Failed to probe video properties")

            width, height = dimensions

            await job_manager.update_job(job_id, {
                "duration": duration,
                "message": "Building FFmpeg command..."
            })

            # Build FFmpeg command with overlay files support
            cmd = FFmpegHelper.build_command(
                input_path,
                str(output_path),
                overlays,
                width,
                height,
                overlay_files
            )
            
            logger.info(f"Executing FFmpeg for job {job_id}: {' '.join(cmd)}")
            
            # Execute FFmpeg with progress tracking
            await job_manager.update_job(job_id, {
                "message": "Processing video..."
            })
            
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Monitor progress
            while True:
                line = await process.stderr.readline()
                if not line:
                    break
                
                decoded = line.decode('utf-8', errors='ignore').strip()
                
                # Extract progress
                progress = FFmpegHelper.extract_progress_from_line(decoded, duration)
                if progress is not None:
                    await job_manager.update_job(job_id, {
                        "progress": progress,
                        "message": f"Processing: {progress}%"
                    })
            
            # Wait for completion
            await process.wait()
            
            if process.returncode != 0:
                stderr_output = await process.stderr.read()
                error_msg = stderr_output.decode('utf-8', errors='ignore')[-500:]
                raise Exception(f"FFmpeg failed with code {process.returncode}: {error_msg}")
            
            # Verify output file exists
            if not output_path.exists():
                raise Exception("Output file was not created")
            
            # Success
            await job_manager.update_job(job_id, {
                "status": JobStatus.DONE,
                "progress": 100,
                "message": "Processing complete",
                "result_path": str(output_path),
                "completed_at": datetime.utcnow().isoformat()
            })
            
            logger.info(f"Job {job_id} completed successfully")
        
        except Exception as e:
            logger.error(f"Job {job_id} failed: {str(e)}")
            await job_manager.update_job(job_id, {
                "status": JobStatus.ERROR,
                "message": f"Processing failed: {str(e)}",
                "completed_at": datetime.utcnow().isoformat()
            })

# Global processor instance
video_processor = VideoProcessor()