import logging
import os
from pathlib import Path
from typing import List

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.jobs import job_store
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

app = FastAPI(
    title="AI Property Video Generator",
    description="Web service for turning property details and images into promotional videos",
    version="0.1.0",
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


# Serve root index.html
@app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
async def serve_index():
    return FileResponse(STATIC_DIR / "index.html")

# Mount static files
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

if __name__ == "__main__":
    import uvicorn
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("app.main:app", host=host, port=port, reload=True)
