import json
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.jobs import job_store, run_video_generation_job
from app.schemas import FieldError, JobResponse, ValidationErrorResponse
from app.validators import parse_and_validate_property_data, validate_and_filter_images

# Load environment variables
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = Path(__file__).resolve().parent / "static"
LOGS_DIR = BASE_DIR / "logs"
OUTPUTS_DIR = BASE_DIR / "outputs"

# Ensure runtime directories exist
LOGS_DIR.mkdir(parents=True, exist_ok=True)
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOGS_DIR / "app.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("property_video_gen")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: clean up output directories older than 24h
    logger.info("Executing startup cleanup for expired jobs...")
    job_store.cleanup_old_jobs(max_age_hours=24)
    yield


app = FastAPI(
    title="AI Property Video Generator",
    description="Web service for turning property details and images into promotional videos",
    version="0.1.0",
    lifespan=lifespan,
)

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.api_route("/api/health", methods=["GET", "HEAD"])
@app.api_route("/health", methods=["GET", "HEAD"], include_in_schema=False)
async def health_check():
    """Health check endpoint to verify service availability."""
    return {
        "status": "ok",
        "service": "property-video-generator",
        "version": "0.1.0",
    }


@app.post(
    "/api/generate",
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        202: {"description": "Job queued successfully"},
        422: {"model": ValidationErrorResponse, "description": "Validation errors"},
    },
)
async def generate_video(
    request: Request,
    background_tasks: BackgroundTasks,
    property_name: str = Form(""),
    location: str = Form(""),
    price: str = Form(""),
    property_type: str = Form(""),
    bedrooms: str = Form(""),
    area: str = Form(""),
    key_features: str = Form(""),
    contact_cta: str = Form(""),
    voiceover_enabled: str = Form("true"),
    script_mode: str = Form("template"),
    images: List[UploadFile] = File(...),
):
    """
    Validate property inputs and images, queue generation job, and return job_id.
    Returns field-level errors as JSON {errors: [{field, message}]} if validation fails.
    """
    form_data = {
        "property_name": property_name,
        "location": location,
        "price": price,
        "property_type": property_type,
        "bedrooms": bedrooms,
        "area": area,
        "key_features": key_features,
        "contact_cta": contact_cta,
        "voiceover_enabled": voiceover_enabled,
        "script_mode": script_mode,
    }

    # 1. Validate property data fields
    prop_input, field_errors = parse_and_validate_property_data(form_data)

    # 2. Read and validate uploaded images
    image_tuples = []
    if images:
        for img in images:
            content = await img.read()
            image_tuples.append((img.filename or "image.jpg", content, img.content_type or ""))

    valid_images, image_warnings, image_errors = validate_and_filter_images(image_tuples)
    field_errors.extend(image_errors)

    if field_errors:
        return JSONResponse(
            status_code=422,
            content={"errors": [err.model_dump() for err in field_errors]},
        )

    # 3. Create job in queue
    warnings = list(image_warnings)
    job = job_store.create(warnings=warnings)

    # 4. Dispatch background generation pipeline
    background_tasks.add_task(
        run_video_generation_job,
        job.job_id,
        prop_input,
        valid_images,
    )

    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content={
            "job_id": job.job_id,
            "status": job.status,
            "message": "Job queued successfully",
            "warnings": warnings,
        },
    )


@app.get("/api/jobs/{job_id}", response_model=JobResponse)
async def get_job_status(job_id: str):
    """Retrieve the current progress and status of a video generation job."""
    job = job_store.get(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job with ID '{job_id}' not found",
        )
    return job.to_response()


@app.get("/api/sample-data")
async def get_sample_data():
    """Returns sample property data and image paths for the 'Load sample data' feature."""
    sample_file = BASE_DIR / "sample_data" / "sample.json"
    if not sample_file.exists():
        raise HTTPException(status_code=404, detail="sample.json not found")

    with open(sample_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Gather sample images (prefer tests/test_images if available)
    test_images_dir = BASE_DIR / "tests" / "test_images"
    sample_images_dir = BASE_DIR / "sample_data" / "images"
    image_urls = []

    active_dir = (
        test_images_dir
        if (test_images_dir.exists() and any(test_images_dir.iterdir()))
        else sample_images_dir
    )
    url_prefix = "/tests/test_images" if active_dir == test_images_dir else "/sample_data/images"

    if active_dir.exists():
        for img_name in sorted(os.listdir(active_dir)):
            if img_name.lower().endswith((".jpg", ".jpeg", ".png", ".webp")):
                image_urls.append(f"{url_prefix}/{img_name}")

    data["images"] = image_urls
    return data


@app.get("/api/jobs/{job_id}/video")
async def get_job_video(job_id: str):
    """Serve the generated MP4 video file for a completed job."""
    video_path = OUTPUTS_DIR / job_id / "video.mp4"
    if not video_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Video for job '{job_id}' is not yet available",
        )
    return FileResponse(
        str(video_path),
        media_type="video/mp4",
        filename=f"property_video_{job_id}.mp4",
    )


# Serve root index.html
@app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
async def serve_index():
    return FileResponse(STATIC_DIR / "index.html")

# Mount static files, sample data, and test images
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/sample_data", StaticFiles(directory=str(BASE_DIR / "sample_data")), name="sample_data")
if (BASE_DIR / "tests" / "test_images").exists():
    app.mount("/tests/test_images", StaticFiles(directory=str(BASE_DIR / "tests" / "test_images")), name="test_images")

if __name__ == "__main__":
    import uvicorn
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("app.main:app", host=host, port=port, reload=True)
