"""
Image job runner — shared worker used by both the direct endpoint (via FastAPI
BackgroundTasks) and the chat path (via a daemon thread, since an SSE response
has no BackgroundTasks hook).  Keeping the worker here avoids api→api imports and
guarantees identical behavior on both paths.
"""
from __future__ import annotations

import threading

from companion.images.jobs import create_job, finish_error, finish_ok
from companion.visual_support.schemas import VisualSupportRequest
from companion.visual_support.service import VisualSupportService


def run_image_job(job_id: str, vsr: VisualSupportRequest) -> None:
    """Generate the image and record the outcome on the job."""
    try:
        response = VisualSupportService().generate(vsr)
        finish_ok(
            job_id,
            image_url=response.image_url,  # relative; poll endpoint absolutizes
            meta={
                "provider": response.provider,
                "model": response.model,
                "scope": response.scope,
                "frame_count": response.frame_count,
                "cached": response.cached,
                "mock": response.mock,
                "estimated_cost_usd": response.estimated_cost_usd,
                "elapsed_seconds": response.elapsed_seconds,
            },
        )
    except Exception as exc:  # noqa: BLE001 — surfaced via job status
        finish_error(job_id, error=str(exc))


def start_image_job_thread(vsr: VisualSupportRequest) -> str:
    """Create a job and run it in a background daemon thread. Returns job_id.

    Used by the chat path, where FastAPI BackgroundTasks are unavailable."""
    job = create_job()
    threading.Thread(
        target=run_image_job, args=(job.job_id, vsr), daemon=True
    ).start()
    return job.job_id
