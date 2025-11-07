import json
from datetime import datetime, timedelta
from typing import Dict, Optional
import asyncio
from pathlib import Path

from app.models import JobStatus
from app.config import settings

class JobManager:
    """Manages job state with optional Redis support"""
    
    def __init__(self):
        self.jobs: Dict[str, Dict] = {}
        self.redis_client = None
        self._cleanup_task = None
        
        if settings.USE_REDIS and settings.REDIS_URL:
            try:
                import redis.asyncio as redis
                self.redis_client = redis.from_url(settings.REDIS_URL)
            except ImportError:
                print("Redis not available, using in-memory storage")
    
    async def create_job(self, job_id: str, video_path: str) -> Dict:
        """Create a new job entry"""
        job_data = {
            "status": JobStatus.QUEUED,
            "progress": 0,
            "message": "Job queued",
            "video_path": video_path,
            "result_path": None,
            "created_at": datetime.utcnow().isoformat(),
            "completed_at": None,
            "duration": None
        }
        
        if self.redis_client:
            await self.redis_client.setex(
                f"job:{job_id}",
                timedelta(hours=settings.JOB_RETENTION_HOURS),
                json.dumps(job_data)
            )
        else:
            self.jobs[job_id] = job_data
        
        return job_data
    
    async def get_job(self, job_id: str) -> Optional[Dict]:
        """Retrieve job data"""
        if self.redis_client:
            data = await self.redis_client.get(f"job:{job_id}")
            return json.loads(data) if data else None
        else:
            return self.jobs.get(job_id)
    
    async def update_job(self, job_id: str, updates: Dict) -> bool:
        """Update job data"""
        job = await self.get_job(job_id)
        if not job:
            return False
        
        job.update(updates)
        
        if self.redis_client:
            await self.redis_client.setex(
                f"job:{job_id}",
                timedelta(hours=settings.JOB_RETENTION_HOURS),
                json.dumps(job)
            )
        else:
            self.jobs[job_id] = job
        
        return True
    
    async def delete_job(self, job_id: str) -> bool:
        """Delete job data"""
        if self.redis_client:
            await self.redis_client.delete(f"job:{job_id}")
        else:
            if job_id in self.jobs:
                del self.jobs[job_id]
        return True
    
    async def cleanup_old_jobs(self):
        """Background task to clean up old completed jobs"""
        while True:
            try:
                await asyncio.sleep(3600)  # Run every hour
                
                cutoff = datetime.utcnow() - timedelta(hours=settings.JOB_RETENTION_HOURS)
                
                if self.redis_client:
                    # Redis handles expiry automatically
                    pass
                else:
                    # Manual cleanup for in-memory storage
                    to_delete = []
                    for job_id, job in self.jobs.items():
                        if job.get('completed_at'):
                            completed = datetime.fromisoformat(job['completed_at'])
                            if completed < cutoff:
                                to_delete.append(job_id)
                                # Clean up files
                                self._cleanup_job_files(job)
                    
                    for job_id in to_delete:
                        del self.jobs[job_id]
                        print(f"Cleaned up job {job_id}")
            
            except Exception as e:
                print(f"Error in cleanup task: {e}")
    
    def _cleanup_job_files(self, job: Dict):
        """Delete associated files for a job"""
        try:
            if job.get('video_path'):
                Path(job['video_path']).unlink(missing_ok=True)
            if job.get('result_path'):
                Path(job['result_path']).unlink(missing_ok=True)
        except Exception as e:
            print(f"Error cleaning up files: {e}")
    
    def start_cleanup_task(self):
        """Start the background cleanup task"""
        if not self._cleanup_task:
            self._cleanup_task = asyncio.create_task(self.cleanup_old_jobs())
    
    async def shutdown(self):
        """Cleanup on shutdown"""
        if self._cleanup_task:
            self._cleanup_task.cancel()
        if self.redis_client:
            await self.redis_client.close()

# Global job manager instance
job_manager = JobManager()