from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path

from app.models import JobStatusResponse, JobStatus
from app.services.job_manager import job_manager

router = APIRouter(prefix="/api/v1", tags=["jobs"])

@router.get("/status/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str):
    """
    Get the current status of a processing job.
    
    Returns job status, progress percentage, and current message.
    """
    job = await job_manager.get_job(job_id)
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    return JobStatusResponse(
        job_id=job_id,
        status=job["status"],
        progress=job["progress"],
        message=job.get("message", ""),
        created_at=job.get("created_at"),
        completed_at=job.get("completed_at")
    )

@router.get("/result/{job_id}")
async def get_job_result(job_id: str):
    """
    Download the processed video file.
    
    Only available when job status is 'done'.
    """
    job = await job_manager.get_job(job_id)
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    if job["status"] != JobStatus.DONE:
        raise HTTPException(
            status_code=400,
            detail=f"Result not ready. Current status: {job['status']}"
        )
    
    result_path = job.get("result_path")
    if not result_path or not Path(result_path).exists():
        raise HTTPException(status_code=404, detail="Result file not found")
    
    return FileResponse(
        result_path,
        media_type="video/mp4",
        filename=Path(result_path).name,
        headers={
            "Content-Disposition": f'attachment; filename="{Path(result_path).name}"'
        }
    )

@router.delete("/job/{job_id}")
async def delete_job(job_id: str):
    """
    Delete a job and its associated files.
    
    Useful for cleaning up after downloading results.
    """
    job = await job_manager.get_job(job_id)
    
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    
    # Delete files
    try:
        if job.get("video_path"):
            Path(job["video_path"]).unlink(missing_ok=True)
        if job.get("result_path"):
            Path(job["result_path"]).unlink(missing_ok=True)
    except Exception as e:
        print(f"Error deleting files: {e}")
    
    # Delete job record
    await job_manager.delete_job(job_id)
    
    return {"message": "Job deleted successfully"}