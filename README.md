# Buttercut.ai API - Backend (FastAPI + FFmpeg)

A production-ready FastAPI backend for processing videos with text, image, and video clip overlays using FFmpeg. This backend receives videos and overlay metadata from the frontend, processes them asynchronously, and returns downloadable rendered videos.

## Architecture Overview

```
app/
├── config.py              # Configuration management
├── main.py               # FastAPI application entry point
├── models.py             # Pydantic models
├── routers/
│   ├── upload.py         # Video upload endpoint
│   └── jobs.py           # Status & result endpoints
├── services/
│   ├── job_manager.py    # Job state management
│   └── video_processor.py # FFmpeg processing
└── utils/
    ├── validators.py     # Input validation
    └── ffmpeg.py         # FFmpeg utilities
```

## Features

### Core Functionality
- Async video processing with FFmpeg
- Text overlay with customizable positioning and timing
- Real-time progress tracking
- Job queue management with concurrency limits

### Security
- File type and size validation
- Filename sanitization (prevents path traversal)
- MIME type verification
- Input validation with Pydantic

### Production Ready
- Modular, testable architecture
- Structured error handling and logging
- CORS configuration
- Automatic cleanup of old jobs
- Optional Redis support for scalability
- Graceful shutdown handling

## Installation

### Prerequisites
- Python 3.9+
- FFmpeg installed and in PATH

### Setup

1. **Install dependencies:**
```bash
pip install -r requirements.txt
```

2. **Install FFmpeg:**
```bash
# Ubuntu/Debian
sudo apt-get install ffmpeg

# macOS
brew install ffmpeg

# Windows
Download from https://ffmpeg.org/download.html
```

3. **Create `.env` file:**
```env
# Directories
UPLOAD_DIR=uploads
RESULTS_DIR=results

# File constraints
MAX_FILE_SIZE=524288000  # 500MB in bytes
MAX_CONCURRENT_JOBS=5

# Redis (optional)
# REDIS_URL=redis://localhost:6379
# USE_REDIS=true

# API settings
CORS_ORIGINS=["http://localhost:3000","http://localhost:5173"]
```

4. **Run the server:**
```bash
# Development
source .venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Production
gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

## API Usage

### 1. Upload Video

```bash
curl -X POST "http://localhost:8000/api/v1/upload" \
  -F "video=@input.mp4" \
  -F 'metadata={
    "overlays": [
      {
        "type": "text",
        "content": "Hello World",
        "x": 100,
        "y": 100,
        "start_time": 0,
        "end_time": 5,
        "font_size": 36,
        "color": "white"
      }
    ]
  }'
```

**Response:**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "Video uploaded successfully. Processing started."
}
```

### 2. Check Status

```bash
curl "http://localhost:8000/api/v1/status/550e8400-e29b-41d4-a716-446655440000"
```

**Response:**
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "processing",
  "progress": 45,
  "message": "Processing: 45%",
  "created_at": "2024-01-15T10:30:00",
  "completed_at": null
}
```

### 3. Download Result

```bash
curl -O "http://localhost:8000/api/v1/result/550e8400-e29b-41d4-a716-446655440000"
```

### 4. Delete Job (Optional)

```bash
curl -X DELETE "http://localhost:8000/api/v1/job/550e8400-e29b-41d4-a716-446655440000"
```

## Overlay Configuration

### Text Overlay
```json
{
  "type": "text",
  "content": "Your text here",
  "x": 100,              // X position in pixels
  "y": 100,              // Y position in pixels
  "start_time": 0,       // Start time in seconds
  "end_time": 5,         // End time in seconds
  "font_size": 24,       // Font size (8-200)
  "color": "white",      // Text color
  "opacity": 1.0         // Opacity (0.0-1.0)
}
```

### Image Overlay (Extended)
```json
{
  "type": "image",
  "content": "/path/to/image.png",
  "x": 50,
  "y": 50,
  "start_time": 0,
  "end_time": 10,
  "scale": 1.0,
  "opacity": 0.8
}
```

## Configuration Options

All settings can be configured via environment variables or `.env` file:

| Variable | Default | Description |
|----------|---------|-------------|
| `UPLOAD_DIR` | `uploads` | Directory for uploaded videos |
| `RESULTS_DIR` | `results` | Directory for processed videos |
| `MAX_FILE_SIZE` | `524288000` | Max upload size (bytes) |
| `MAX_CONCURRENT_JOBS` | `5` | Max simultaneous processing jobs |
| `JOB_RETENTION_HOURS` | `24` | Hours to keep completed jobs |
| `REDIS_URL` | `None` | Redis connection URL |
| `USE_REDIS` | `false` | Enable Redis for job storage |

## Testing

```bash
# Run tests
pytest

# Run with coverage
pytest --cov=app tests/

# Run specific test file
pytest tests/test_upload.py
```

## Why Modular?

### Benefits
1. **Testability**: Each module can be tested independently
2. **Maintainability**: Clear separation of concerns
3. **Scalability**: Easy to add new features or swap implementations
4. **Reusability**: Components can be used in other projects
5. **Team Collaboration**: Multiple developers can work on different modules

### Key Design Decisions

- **Job Manager**: Abstracts storage (in-memory or Redis) for easy scaling
- **Video Processor**: Isolated FFmpeg logic with progress tracking
- **Validators**: Centralized security checks
- **FFmpeg Utils**: Reusable FFmpeg command builders
- **Routers**: Clean API structure following REST principles

## Performance Optimization

1. **Concurrency Control**: `MAX_CONCURRENT_JOBS` prevents server overload
2. **Async Processing**: Non-blocking job execution
3. **Progress Tracking**: Efficient stderr parsing without buffering
4. **File Cleanup**: Automatic removal of old files
5. **Redis Support**: Horizontal scaling with shared state

## Error Handling

All endpoints return consistent error responses:

```json
{
  "detail": "Error description",
  "error_code": "SPECIFIC_ERROR_CODE"
}
```

Common error codes:
- `400`: Invalid input (malformed JSON, invalid file type)
- `404`: Job not found
- `422`: Validation error (detailed field errors)
- `500`: Server error (logged for debugging)

## Troubleshooting

**FFmpeg not found:**
```bash
which ffmpeg  # Should return path
```

**Permission denied on upload:**
```bash
chmod 755 uploads results
```