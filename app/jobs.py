"""Job management and in-memory store for video generation tasks."""

import logging
import threading
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from app.schemas import JobResponse, JobStatus, ScriptOutput

logger = logging.getLogger("property_video_gen.jobs")


class Job:
    def __init__(self, job_id: str, warnings: Optional[List[str]] = None):
        self.job_id = job_id
        self.status: JobStatus = JobStatus.QUEUED
        self.progress: int = 0
        self.message: str = "Job queued"
        self.warnings: List[str] = warnings or []
        self.video_url: Optional[str] = None
        self.script: Optional[ScriptOutput] = None
        self.created_at: datetime = datetime.now()
        self.updated_at: datetime = datetime.now()
        self.output_dir: Optional[str] = None

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
        if warning:
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
                del self._jobs[jid]
                removed += 1
        if removed:
            logger.info(f"Cleaned up {removed} old jobs")
        return removed


# Global singleton job store
job_store = JobStore()
