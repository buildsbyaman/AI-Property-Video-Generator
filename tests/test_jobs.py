import io
import os
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from app.jobs import JobStore, job_store, run_video_generation_job
from app.schemas import JobStatus, PropertyInput, PropertyType, ScriptMode


def make_test_image_bytes(color: str) -> bytes:
    buf = io.BytesIO()
    img = Image.new("RGB", (1280, 720), color=color)
    img.save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture
def sample_prop() -> PropertyInput:
    return PropertyInput(
        property_name="Ocean Crest Villa",
        location="Malibu, CA",
        price="$3,850,000",
        property_type=PropertyType.VILLA,
        bedrooms="5 Beds",
        area="4,200 sq ft",
        key_features=["Private Beach Access", "Infinity Edge Pool", "Designer Chef Kitchen"],
        contact_cta="Call 310-555-0100 to arrange a tour",
        voiceover_enabled=False,  # faster unit test run without network TTS
        script_mode=ScriptMode.TEMPLATE,
    )


def test_job_lifecycle_full_pipeline(sample_prop):
    # 4 images
    images = [
        (f"img_{i}.jpg", make_test_image_bytes(col))
        for i, col in enumerate(["#1E3A8A", "#065F46", "#831843", "#78350F"])
    ]

    job = job_store.create(warnings=["Test warning"])
    job_id = job.job_id
    assert job.status == JobStatus.QUEUED

    # Execute background worker
    run_video_generation_job(job_id, sample_prop, images)

    updated_job = job_store.get(job_id)
    assert updated_job is not None
    assert updated_job.status == JobStatus.DONE
    assert updated_job.progress == 100
    assert updated_job.video_url == f"/api/jobs/{job_id}/video"
    assert updated_job.script is not None

    # Check generated video file
    video_file = updated_job.output_dir / "video.mp4"
    assert video_file.exists()
    assert video_file.stat().st_size > 5000


def test_job_error_handling_graceful(sample_prop):
    # Provide corrupted images (< 4 valid) to trigger error branch
    corrupt_images = [
        ("corrupt1.jpg", b"bad_data"),
        ("corrupt2.jpg", b"bad_data"),
    ]

    job = job_store.create()
    run_video_generation_job(job.job_id, sample_prop, corrupt_images)

    assert job.status == JobStatus.ERROR
    assert "valid images" in job.message.lower()


def test_job_store_cleanup_24h(tmp_path):
    store = JobStore()
    job = store.create()

    # Create dummy output directory
    job.output_dir = tmp_path / "old_job_123"
    job.output_dir.mkdir(parents=True, exist_ok=True)
    dummy_file = job.output_dir / "video.mp4"
    dummy_file.write_text("dummy")

    # Set created_at to 25 hours ago
    job.created_at = datetime.now() - timedelta(hours=25)

    with patch("app.jobs.OUTPUTS_DIR", tmp_path):
        removed_count = store.cleanup_old_jobs(max_age_hours=24)
        assert removed_count >= 1
        assert store.get(job.job_id) is None
        assert not job.output_dir.exists()
