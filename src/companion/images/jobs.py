"""
In-memory async job store for image generation.

MVP scope: single-process uvicorn, no persistence.  Jobs live in a module-level
dict and are lost on restart — acceptable because images are cheap to regenerate
and there is no durable user session.  A lock guards the dict since FastAPI runs
`BackgroundTasks` in a worker thread.

If we ever run multiple workers or need durability, swap this module for Redis /
a DB table without touching the endpoint contract (create_job/get_job/finish).
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from typing import Literal

JobStatus = Literal["pending", "done", "error"]


@dataclass
class ImageJob:
    job_id: str
    status: JobStatus = "pending"
    image_url: str | None = None   # relative, e.g. "/generated-visuals/x.png"
    error: str | None = None
    meta: dict = field(default_factory=dict)  # provider, model, scope, cost…


_JOBS: dict[str, ImageJob] = {}
_LOCK = threading.Lock()


def create_job() -> ImageJob:
    job = ImageJob(job_id=uuid.uuid4().hex)
    with _LOCK:
        _JOBS[job.job_id] = job
    return job


def get_job(job_id: str) -> ImageJob | None:
    with _LOCK:
        return _JOBS.get(job_id)


def finish_ok(job_id: str, *, image_url: str, meta: dict | None = None) -> None:
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            return
        job.status = "done"
        job.image_url = image_url
        if meta:
            job.meta = meta


def finish_error(job_id: str, *, error: str) -> None:
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            return
        job.status = "error"
        job.error = error
