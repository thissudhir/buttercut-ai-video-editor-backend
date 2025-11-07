import os
import magic
from pathlib import Path
from fastapi import HTTPException
from starlette.datastructures import UploadFile
from typing import Optional

from app.config import settings

class FileValidator:
    """Validates uploaded files for security and compatibility"""
    
    @staticmethod
    async def validate_video(file: UploadFile) -> None:
        """Validate video file"""
        # Check filename
        if not file.filename:
            raise HTTPException(status_code=400, detail="Filename is required")
        
        # Sanitize filename
        safe_filename = FileValidator._sanitize_filename(file.filename)
        
        # Check extension
        ext = Path(safe_filename).suffix.lower()
        if ext not in settings.ALLOWED_VIDEO_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type. Allowed: {settings.ALLOWED_VIDEO_EXTENSIONS}"
            )
        
        # Check file size by reading content
        content = await file.read()
        if len(content) > settings.MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"File too large. Max size: {settings.MAX_FILE_SIZE / 1024 / 1024}MB"
            )
        
        # Reset file pointer for later use
        await file.seek(0)
        
        # Optional: Check MIME type (requires python-magic)
        try:
            mime = magic.from_buffer(content[:2048], mime=True)
            if not mime.startswith('video/'):
                raise HTTPException(status_code=400, detail="File is not a valid video")
        except Exception:
            # python-magic not available, skip MIME check
            pass
    
    @staticmethod
    def _sanitize_filename(filename: str) -> str:
        """Remove potentially dangerous characters from filename"""
        # Remove path separators and null bytes
        safe = filename.replace('/', '_').replace('\\', '_').replace('\0', '')
        # Remove leading dots to prevent hidden files
        safe = safe.lstrip('.')
        # Limit length
        name = Path(safe).stem[:100]
        ext = Path(safe).suffix[:10]
        return f"{name}{ext}"
    
    @staticmethod
    def validate_overlay_content(overlay_type: str, content: str, check_exists: bool = False) -> None:
        """Validate overlay content based on type

        Args:
            overlay_type: Type of overlay (text, image, video)
            content: Content string (text, filename, or URL)
            check_exists: If True, verify file exists on disk (only for already-saved files)
        """
        if overlay_type == "text":
            if len(content) > 500:
                raise HTTPException(status_code=400, detail="Text overlay too long (max 500 chars)")
        elif overlay_type in ("image", "video"):
            # If it's a URL or data URI, just validate format
            if content.startswith(('http://', 'https://', 'data:')):
                return

            # If it's a simple filename (no path separators), it's being uploaded - skip existence check
            if '/' not in content and '\\' not in content:
                # Just validate the filename is safe
                safe_name = FileValidator._sanitize_filename(content)
                if not safe_name:
                    raise HTTPException(status_code=400, detail="Invalid filename")
                return

            # Only check existence if explicitly requested (for already-saved files)
            if check_exists:
                path = Path(content)
                if not path.is_absolute():
                    path = Path(settings.UPLOAD_DIR) / path
                if not path.exists():
                    raise HTTPException(status_code=400, detail=f"Overlay file not found: {content}")
                # Prevent path traversal
                try:
                    path.resolve().relative_to(Path(settings.UPLOAD_DIR).resolve())
                except ValueError:
                    raise HTTPException(status_code=400, detail="Invalid file path")