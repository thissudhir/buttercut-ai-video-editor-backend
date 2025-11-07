from pydantic import BaseModel, Field, validator
from typing import List, Optional, Literal
from enum import Enum

class JobStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    DONE = "done"
    ERROR = "error"

class OverlayType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"

class Overlay(BaseModel):
    """Single overlay configuration"""
    type: OverlayType
    content: str
    x: float = Field(ge=0, description="X position in pixels (will be rounded)")
    y: float = Field(ge=0, description="Y position in pixels (will be rounded)")
    start_time: float = Field(ge=0, description="Start time in seconds")
    end_time: float = Field(gt=0, description="End time in seconds")
    
    # Text-specific
    font_size: Optional[int] = Field(24, ge=8, le=200)
    color: Optional[str] = "white"
    
    # Image/video-specific
    scale: Optional[float] = Field(1.0, gt=0, le=5)
    opacity: Optional[float] = Field(1.0, ge=0, le=1)
    
    @validator('end_time')
    def end_after_start(cls, v, values):
        if 'start_time' in values and v <= values['start_time']:
            raise ValueError('end_time must be greater than start_time')
        return v

class OverlayMetadata(BaseModel):
    """Complete overlay metadata"""
    overlays: List[Overlay] = Field(default_factory=list)

class JobResponse(BaseModel):
    """Response for job creation"""
    job_id: str
    message: str = "Job created successfully"

class JobStatusResponse(BaseModel):
    """Response for job status query"""
    job_id: str
    status: JobStatus
    progress: int = Field(ge=0, le=100)
    message: str = ""
    created_at: Optional[str] = None
    completed_at: Optional[str] = None

class ErrorResponse(BaseModel):
    """Standard error response"""
    detail: str
    error_code: Optional[str] = None