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
    """Single overlay configuration - matches frontend types exactly"""
    # Core properties
    id: Optional[str] = None
    type: OverlayType
    content: str
    x: float = Field(ge=0, description="X position in pixels")
    y: float = Field(ge=0, description="Y position in pixels")
    width: Optional[float] = Field(200, gt=0, description="Width in pixels")
    height: Optional[float] = Field(100, gt=0, description="Height in pixels")
    start_time: float = Field(ge=0, description="Start time in seconds")
    end_time: float = Field(gt=0, description="End time in seconds")

    # Transform properties
    opacity: Optional[float] = Field(1.0, ge=0, le=1, description="Opacity 0-1")
    rotation: Optional[float] = Field(0, description="Rotation in degrees")
    scale: Optional[float] = Field(1.0, gt=0, description="Scale multiplier")
    zIndex: Optional[int] = Field(0, description="Layer order")

    # Text-specific properties
    fontSize: Optional[int] = Field(24, ge=8, le=200, description="Font size in pixels")
    fontColor: Optional[str] = Field("white", description="Text color")
    color: Optional[str] = Field(None, description="Alias for fontColor")  # Legacy support
    fontFamily: Optional[str] = Field("sans-serif", description="Font family")
    textAlign: Optional[Literal["left", "center", "right"]] = Field("left")
    fontWeight: Optional[Literal["normal", "bold"]] = Field("normal")

    # State properties
    locked: Optional[bool] = Field(False, description="Prevent editing")
    visible: Optional[bool] = Field(True, description="Show/hide overlay")

    @validator('end_time')
    def end_after_start(cls, v, values):
        if 'start_time' in values and v <= values['start_time']:
            raise ValueError('end_time must be greater than start_time')
        return v

    @validator('fontColor', always=True)
    def set_font_color(cls, v, values):
        """Use color if fontColor not provided (legacy support)"""
        if v is None and 'color' in values and values['color']:
            return values['color']
        return v or "white"

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
