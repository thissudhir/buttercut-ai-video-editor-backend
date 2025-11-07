import os
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    """Application settings with environment variable support"""
    
    # Directories
    UPLOAD_DIR: str = "uploads"
    RESULTS_DIR: str = "results"
    
    # File constraints
    MAX_FILE_SIZE: int = 500 * 1024 * 1024  # 500MB
    ALLOWED_VIDEO_EXTENSIONS: set = {".mp4", ".avi", ".mov", ".mkv", ".webm"}
    ALLOWED_IMAGE_EXTENSIONS: set = {".png", ".jpg", ".jpeg", ".gif"}
    
    # Job management
    JOB_RETENTION_HOURS: int = 24
    MAX_CONCURRENT_JOBS: int = 5
    
    # Redis (optional)
    REDIS_URL: Optional[str] = None
    USE_REDIS: bool = False
    
    # API settings
    API_TITLE: str = "Buttercut.ai API"
    API_VERSION: str = "1.0.0"
    CORS_ORIGINS: list = ["http://localhost:3000", "http://localhost:5173"]
    
    # FFmpeg
    FFMPEG_PATH: str = "ffmpeg"
    FFPROBE_PATH: str = "ffprobe"
    
    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()

# Ensure directories exist
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
os.makedirs(settings.RESULTS_DIR, exist_ok=True)