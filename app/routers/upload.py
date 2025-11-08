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

        # Log all form fields for debugging
        print(f"DEBUG: Form data keys: {list(form_data.keys())}")
        for key in form_data.keys():
            value = form_data.get(key)
            if isinstance(value, UploadFile):
                print(f"DEBUG: Key '{key}' -> UploadFile: {value.filename}")
            else:
                print(f"DEBUG: Key '{key}' -> Type: {type(value)}, Value preview: {str(value)[:100]}")

        # Extract main video file
        video = form_data.get("video")
        if not video or not isinstance(video, UploadFile):
            raise HTTPException(status_code=400, detail="Video file is required")

        # Validate video file
        await FileValidator.validate_video(video)
        print(f"DEBUG: Video validation passed: {video.filename}")

        # Extract and parse metadata
        metadata_str = form_data.get("metadata")
        if not metadata_str:
            raise HTTPException(status_code=400, detail="Metadata is required")

        try:
            metadata_dict = json.loads(metadata_str)
            print(f"DEBUG: Metadata parsed successfully")
            print(f"DEBUG: Number of overlays: {len(metadata_dict.get('overlays', []))}")

            overlay_data = OverlayMetadata(**metadata_dict)

            # Log each overlay details
            for i, overlay in enumerate(overlay_data.overlays):
                print(f"DEBUG: Overlay {i}: type={overlay.type}, content={overlay.content}")

        except json.JSONDecodeError as e:
            print(f"DEBUG: JSON decode error: {e}")
            raise HTTPException(status_code=400, detail="Invalid JSON in metadata")
        except Exception as e:
            print(f"DEBUG: Metadata validation error: {e}")
            raise HTTPException(status_code=400, detail=f"Invalid metadata: {str(e)}")

        # Validate overlay content
        for i, overlay in enumerate(overlay_data.overlays):
            try:
                FileValidator.validate_overlay_content(overlay.type, overlay.content)
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

        print(f"DEBUG: Saved main video to: {video_path}")

        # Dictionary to store overlay file paths
        # Key: original content string from overlay (URI or filename)
        # Value: path to saved file
        overlay_files = {}

        # Track uploaded files by their form field key (overlay_file_N)
        # The N corresponds to the overlay's index in the overlays array
        uploaded_files_by_index = {}

        # Process overlay files (overlay_file_0, overlay_file_1, etc.)
        for key, value in form_data.items():
            if key.startswith("overlay_file_") and isinstance(value, UploadFile):
                # Extract the index from the form field name (overlay_file_N -> N)
                try:
                    file_index = int(key.replace("overlay_file_", ""))
                except ValueError:
                    print(f"WARNING: Could not extract index from form field '{key}'")
                    continue

                original_filename = value.filename

                # Save overlay file
                safe_overlay_filename = FileValidator._sanitize_filename(original_filename)
                overlay_file_path = Path(settings.UPLOAD_DIR) / f"{job_id}_{safe_overlay_filename}"

                with open(overlay_file_path, "wb") as f:
                    overlay_content = await value.read()
                    f.write(overlay_content)

                # Store the mapping by index
                uploaded_files_by_index[file_index] = str(overlay_file_path)

                print(f"DEBUG: Saved overlay file at index {file_index}: '{original_filename}' -> {overlay_file_path}")

        print(f"DEBUG: Uploaded files by index: {uploaded_files_by_index}")

        # Now map overlay content URIs to saved file paths using the index
        for i, overlay in enumerate(overlay_data.overlays):
            if overlay.type in ["image", "video"]:
                print(f"DEBUG: Processing overlay {i} - type={overlay.type}, content='{overlay.content}'")

                # Check if we have an uploaded file for this index
                if i in uploaded_files_by_index:
                    overlay_files[overlay.content] = uploaded_files_by_index[i]
                    print(f"DEBUG: Overlay {i} - Mapped content '{overlay.content}' to file '{uploaded_files_by_index[i]}'")
                else:
                    print(f"WARNING: Overlay {i} - No uploaded file found for index {i}")
                    print(f"WARNING: Available indices: {list(uploaded_files_by_index.keys())}")

        print(f"DEBUG: Final overlay_files mapping: {overlay_files}")

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
        import traceback
        print(f"ERROR: Upload failed with exception: {e}")
        print(f"ERROR: Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")
