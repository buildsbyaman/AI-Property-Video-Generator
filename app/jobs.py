"""Job management, background runner, in-memory store, and 24h cleanup."""

import logging
import os
import shutil
import threading
import traceback
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from PIL import Image

from app.images import open_and_normalize_image
from app.schemas import JobResponse, JobStatus, PropertyInput, ScriptOutput
from app.script_gen import generate_script
from app.tts import synthesize_script_voiceovers
from app.video import assemble_and_export_video

logger = logging.getLogger("property_video_gen.jobs")

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUTS_DIR = BASE_DIR / "outputs"
ASSETS_AUDIO_PATH = BASE_DIR / "assets" / "audio" / "background.mp3"


class Job:
    def __init__(self, job_id: str, warnings: Optional[List[str]] = None):
        self.job_id = job_id
        self.status: JobStatus = JobStatus.QUEUED
        self.progress: int = 0
        self.message: str = "Job queued"
        self.warnings: List[str] = list(warnings or [])
        self.video_url: Optional[str] = None
        self.script: Optional[ScriptOutput] = None
        self.created_at: datetime = datetime.now()
        self.updated_at: datetime = datetime.now()
        self.output_dir: Path = OUTPUTS_DIR / job_id

    def update(
        self,
        status: Optional[JobStatus] = None,
        progress: Optional[int] = None,
        message: Optional[str] = None,
        warning: Optional[str] = None,
        video_url: Optional[str] = None,
        script: Optional[ScriptOutput] = None,
    ):
        if status is not None:
            self.status = status
        if progress is not None:
            self.progress = max(0, min(100, progress))
        if message is not None:
            self.message = message
        if warning and warning not in self.warnings:
            self.warnings.append(warning)
        if video_url is not None:
            self.video_url = video_url
        if script is not None:
            self.script = script
        self.updated_at = datetime.now()

    def to_response(self) -> JobResponse:
        return JobResponse(
            job_id=self.job_id,
            status=self.status,
            progress=self.progress,
            message=self.message,
            warnings=self.warnings,
            video_url=self.video_url,
            script=self.script,
        )


class JobStore:
    def __init__(self):
        self._jobs: Dict[str, Job] = {}
        self._lock = threading.Lock()

    def create(self, warnings: Optional[List[str]] = None) -> Job:
        job_id = str(uuid.uuid4())[:8]
        job = Job(job_id=job_id, warnings=warnings)
        with self._lock:
            self._jobs[job_id] = job
        logger.info(f"Created job {job_id}")
        return job

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def cleanup_old_jobs(self, max_age_hours: int = 24) -> int:
        threshold = datetime.now() - timedelta(hours=max_age_hours)
        removed = 0
        with self._lock:
            to_remove = [
                jid for jid, job in self._jobs.items()
                if job.created_at < threshold
            ]
            for jid in to_remove:
                job = self._jobs.pop(jid, None)
                if job and job.output_dir.exists():
                    try:
                        shutil.rmtree(job.output_dir)
                    except Exception as e:
                        logger.warning(f"Failed to delete old job output dir {job.output_dir}: {e}")
                removed += 1

        # Also clean unreferenced old directories in outputs/
        if OUTPUTS_DIR.exists():
            for entry in OUTPUTS_DIR.iterdir():
                if entry.is_dir():
                    try:
                        mtime = datetime.fromtimestamp(entry.stat().st_mtime)
                        if mtime < threshold:
                            shutil.rmtree(entry)
                    except Exception as e:
                        logger.warning(f"Could not clean directory {entry}: {e}")

        if removed:
            logger.info(f"Cleaned up {removed} old jobs and output folders.")
        return removed


# Global singleton job store
job_store = JobStore()


def run_video_generation_job(
    job_id: str,
    prop_input: PropertyInput,
    image_tuples: List[Tuple[str, bytes]],
) -> None:
    """
    Background worker pipeline executing the end-to-end video generation:
    1. Scripting (FR-2)
    2. Voice-over Synthesis (FR-3)
    3. Ken Burns Frame & Overlay Generation (FR-3)
    4. Video Assembly, Ducking & MP4 Export (FR-3, FR-5)
    5. Graceful error handling (FR-6)
    """
    job = job_store.get(job_id)
    if not job:
        logger.error(f"Job {job_id} not found in store.")
        return

    job_dir = OUTPUTS_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    job.output_dir = job_dir

    try:
        # --- Stage 1: Scripting ---
        job.update(
            status=JobStatus.SCRIPTING,
            progress=15,
            message="Generating promotional script and scene plan...",
        )
        script, script_warn = generate_script(prop_input, num_images=len(image_tuples))
        if script_warn:
            job.update(warning=script_warn)
        job.update(script=script)

        # --- Stage 2: Voice-over ---
        job.update(
            status=JobStatus.NARRATING,
            progress=35,
            message="Synthesizing scene narration audio...",
        )
        vo_dir = job_dir / "voiceover"
        vo_paths, vo_durs, vo_warns = synthesize_script_voiceovers(
            scenes=script.scenes,
            output_dir=vo_dir,
            voiceover_enabled=prop_input.voiceover_enabled,
        )
        for w in vo_warns:
            job.update(warning=w)

        # --- Stage 3: Prepare Images ---
        job.update(
            status=JobStatus.RENDERING,
            progress=50,
            message="Validating and processing property photos...",
        )
        pil_images: List[Image.Image] = []
        for name, img_bytes in image_tuples:
            img = open_and_normalize_image(img_bytes)
            if img:
                pil_images.append(img)
            else:
                job.update(warning=f"Image '{name}' could not be decoded and was omitted.")

        if len(pil_images) < 4:
            raise ValueError(
                f"Only {len(pil_images)} valid images could be processed. At least 4 are required to render."
            )

        # --- Stage 4: Video Assembly & Export ---
        def on_video_progress(pct: int, stage_str: str, msg: str):
            # Scale video progress (0-100) into overall job progress (50-95%)
            overall = 50 + int(pct * 0.45)
            job.update(
                status=JobStatus.RENDERING,
                progress=overall,
                message=msg,
            )

        output_video_path = job_dir / "video.mp4"
        assemble_and_export_video(
            scenes=script.scenes,
            images=pil_images,
            voiceover_paths=vo_paths,
            voiceover_durations=vo_durs,
            background_audio_path=ASSETS_AUDIO_PATH,
            output_path=output_video_path,
            progress_callback=on_video_progress,
        )

        # Clean up temporary voiceover files
        if vo_dir.exists():
            try:
                shutil.rmtree(vo_dir)
            except Exception:
                pass

        # Complete!
        job.update(
            status=JobStatus.DONE,
            progress=100,
            message="Video generation complete!",
            video_url=f"/api/jobs/{job_id}/video",
        )
        logger.info(f"Job {job_id} completed successfully. Output: {output_video_path}")

    except Exception as exc:
        err_msg = str(exc)
        logger.error(f"Job {job_id} failed: {err_msg}\n{traceback.format_exc()}")
        # Provide human-readable, friendly error message to UI (FR-6)
        if "No such file or directory: 'ffmpeg'" in err_msg or "ffmpeg" in err_msg.lower():
            friendly = "Video encoding failed: FFmpeg executable could not be initialized."
        elif "disk" in err_msg.lower() or "space" in err_msg.lower() or "read-only" in err_msg.lower():
            friendly = "Storage error: could not write output video to disk."
        elif "valid images" in err_msg:
            friendly = err_msg
        else:
            friendly = f"Rendering error: {err_msg}"

        job.update(
            status=JobStatus.ERROR,
            message=friendly,
        )
