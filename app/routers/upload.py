import uuid
import json
from pathlib import Path
import asyncio
from fastapi import APIRouter, File, Form, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.datastructures import UploadFile

from app.models import OverlayMetadata, JobResponse
from app.config import settings
from app.utils.validators import FileValidator
from app.services.job_manager import job_manager
from app.services.video_processor import video_processor

router = APIRouter(prefix="/api/v1", tags=["upload"])

@router.post("/upload", response_model=JobResponse)
async def upload_video(request: Request):
    """
    Upload a video file with overlay metadata.
    Supports additional overlay files (images/videos) via dynamic form fields.

    Accepts:
        - video: Main video file
        - metadata: JSON string with overlay configuration
        - overlay_file_0, overlay_file_1, ...: Optional image/video overlay files

    Returns a job_id that can be used to track processing status.
    """
    try:
        # Parse multipart form data
        form_data = await request.form()

        # Note: Log all form fields
        print(f"DEBUG: Form data keys: {list(form_data.keys())}")
        for key in form_data.keys():
            value = form_data.get(key)
            print(f"DEBUG: Key '{key}' -> Type: {type(value)}, Value preview: {str(value)[:100]}")

        # Extract main video file
        video = form_data.get("video")
        print(f"DEBUG: Video object: {video}, Type: {type(video)}, isinstance check: {isinstance(video, UploadFile)}")
        if not video or not isinstance(video, UploadFile):
            raise HTTPException(status_code=400, detail="Video file is required")

        # Validate video file
        print(f"DEBUG: Starting video validation...")
        try:
            await FileValidator.validate_video(video)
            print(f"DEBUG: Video validation passed")
        except Exception as e:
            print(f"DEBUG: Video validation failed: {e}")
            raise

        # Extract and parse metadata
        metadata_str = form_data.get("metadata")
        print(f"DEBUG: Metadata string: {metadata_str[:200] if metadata_str else 'None'}")
        if not metadata_str:
            raise HTTPException(status_code=400, detail="Metadata is required")

        try:
            metadata_dict = json.loads(metadata_str)
            print(f"DEBUG: Metadata parsed successfully: {metadata_dict}")
            overlay_data = OverlayMetadata(**metadata_dict)
            print(f"DEBUG: OverlayMetadata object created successfully")
        except json.JSONDecodeError as e:
            print(f"DEBUG: JSON decode error: {e}")
            raise HTTPException(status_code=400, detail="Invalid JSON in metadata")
        except Exception as e:
            print(f"DEBUG: Metadata validation error: {e}")
            raise HTTPException(status_code=400, detail=f"Invalid metadata: {str(e)}")

        # Validate overlay content
        print(f"DEBUG: Validating {len(overlay_data.overlays)} overlays...")
        for i, overlay in enumerate(overlay_data.overlays):
            print(f"DEBUG: Validating overlay {i}: type={overlay.type}, content={overlay.content[:50] if overlay.content else 'None'}")
            try:
                FileValidator.validate_overlay_content(overlay.type, overlay.content)
                print(f"DEBUG: Overlay {i} validation passed")
            except Exception as e:
                print(f"DEBUG: Overlay {i} validation failed: {e}")
                raise

        # Generate job ID
        job_id = str(uuid.uuid4())

        # Save video file
        safe_filename = FileValidator._sanitize_filename(video.filename)
        video_path = Path(settings.UPLOAD_DIR) / f"{job_id}_{safe_filename}"

        with open(video_path, "wb") as f:
            content = await video.read()
            f.write(content)

        # Dictionary to store overlay file paths
        overlay_files = {}

        # Dictionary to map original filename to sanitized filename
        filename_mapping = {}

        # Process overlay files (overlay_file_0, overlay_file_1, etc.)
        for key, value in form_data.items():
            if key.startswith("overlay_file_") and isinstance(value, UploadFile):
                original_filename = value.filename
                # Save overlay file
                safe_overlay_filename = FileValidator._sanitize_filename(original_filename)
                overlay_file_path = Path(settings.UPLOAD_DIR) / f"{job_id}_{safe_overlay_filename}"

                with open(overlay_file_path, "wb") as f:
                    overlay_content = await value.read()
                    f.write(overlay_content)

                # Map both original and sanitized filenames to the saved path
                
                overlay_files[safe_overlay_filename] = str(overlay_file_path)
                overlay_files[original_filename] = str(overlay_file_path)
                filename_mapping[original_filename] = safe_overlay_filename

                print(f"DEBUG: Saved overlay file - original: '{original_filename}', sanitized: '{safe_overlay_filename}', path: {overlay_file_path}")

        # Create job
        await job_manager.create_job(job_id, str(video_path))

        # Start processing in background with overlay files mapping
        asyncio.create_task(
            video_processor.process_video(job_id, overlay_data.overlays, overlay_files)
        )

        return JobResponse(
            job_id=job_id,
            message="Video uploaded successfully. Processing started."
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")