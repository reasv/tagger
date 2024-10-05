import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel

from panoptikon.api.routers.jobs.manager import (
    Job,
    JobManager,
    JobModel,
    QueueStatusModel,
)
from panoptikon.api.routers.utils import get_db_readonly, get_db_system_wl
from panoptikon.config import persist_system_config, retrieve_system_config
from panoptikon.db import get_database_connection
from panoptikon.db.extraction_log import get_all_data_logs
from panoptikon.db.files import get_all_file_scans
from panoptikon.db.folders import get_folders_from_database
from panoptikon.types import FileScanRecord, LogRecord, SystemConfig

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/jobs",
    tags=["jobs"],
    responses={404: {"description": "Not found"}},
)

# Initialize FastAPI app and JobManager
job_manager = JobManager()


# Endpoint to get queue status
@router.get(
    "/queue",
    summary="Get running job and queue status",
)
def get_queue_status() -> QueueStatusModel:
    return job_manager.get_queue_status()


# Endpoint to run a data extraction job
@router.post(
    "/data/extraction",
    summary="Run a data extraction job",
)
def enqueue_data_extraction_job(
    inference_ids: List[str] = Query(..., title="Inference ID List"),
    batch_size: Optional[int] = Query(default=None, title="Batch Size"),
    threshold: Optional[float] = Query(
        default=None, title="Confidence Threshold"
    ),
    conn_args: Dict[str, Any] = Depends(get_db_system_wl),
) -> List[JobModel]:
    jobs = []
    for inference_id in inference_ids:
        queue_id = job_manager.get_next_job_id()
        job = Job(
            queue_id=queue_id,
            job_type="data_extraction",
            conn_args=conn_args,
            metadata=inference_id,
            batch_size=batch_size,
            threshold=threshold,
        )
        job_manager.enqueue_job(job)
        jobs.append(
            JobModel(
                queue_id=job.queue_id,
                job_type=job.job_type,
                metadata=job.metadata,
                index_db=job.conn_args["index_db"],
                batch_size=job.batch_size,
                threshold=job.threshold,
            )
        )
    return jobs


# Endpoint to delete extracted data
@router.delete(
    "/data/extraction",
    summary="Delete extracted data",
    status_code=status.HTTP_202_ACCEPTED,
)
def enqueue_delete_extracted_data(
    inference_ids: List[str] = Query(..., title="Inference ID List"),
    conn_args: Dict[str, Any] = Depends(get_db_system_wl),
) -> List[JobModel]:
    jobs = []
    for inference_id in inference_ids:
        queue_id = job_manager.get_next_job_id()
        job = Job(
            queue_id=queue_id,
            job_type="data_deletion",
            conn_args=conn_args,
            metadata=inference_id,
        )
        job_manager.enqueue_job(job)
        jobs.append(
            JobModel(
                queue_id=job.queue_id,
                job_type=job.job_type,
                metadata=job.metadata,
                index_db=job.conn_args["index_db"],
            )
        )
    return jobs


# Endpoint to run a folder rescan
@router.post(
    "/folders/rescan",
    summary="Run a folder rescan",
    status_code=status.HTTP_202_ACCEPTED,
)
def enqueue_folder_rescan(
    conn_args: Dict[str, Any] = Depends(get_db_system_wl),
) -> JobModel:
    queue_id = job_manager.get_next_job_id()
    job = Job(
        queue_id=queue_id,
        job_type="folder_rescan",
        conn_args=conn_args,
    )
    job_manager.enqueue_job(job)
    return JobModel(
        queue_id=job.queue_id,
        job_type=job.job_type,
        metadata=job.metadata,
        index_db=job.conn_args["index_db"],
    )


class Folders(BaseModel):
    included_folders: List[str]
    excluded_folders: List[str]


# Endpoint to update folders
@router.put(
    "/folders",
    summary="Update the folder lists",
    status_code=status.HTTP_202_ACCEPTED,
)
def enqueue_update_folders(
    folders: Folders = Body(
        ...,
        title="The new sets of included and excluded folders. Replaces the current lists with these.",
    ),
    conn_args: Dict[str, Any] = Depends(get_db_system_wl),
) -> JobModel:
    queue_id = job_manager.get_next_job_id()
    job = Job(
        queue_id=queue_id,
        job_type="folder_update",
        conn_args=conn_args,
        included_folders=folders.included_folders,
        excluded_folders=folders.excluded_folders,
    )
    job_manager.enqueue_job(job)
    return JobModel(
        queue_id=job.queue_id,
        job_type=job.job_type,
        metadata=None,
        index_db=job.conn_args["index_db"],
    )


class QueueCancelResponse(BaseModel):
    cancelled_jobs: List[int]


# Endpoint to cancel queued jobs
@router.delete(
    "/queue",
    summary="Cancel queued jobs",
    status_code=status.HTTP_200_OK,
)
def cancel_queued_jobs(
    queue_ids: List[int] = Query(..., title="List of Queue IDs to cancel"),
) -> QueueCancelResponse:
    cancelled = job_manager.cancel_queued_jobs(queue_ids)
    if not cancelled:
        raise HTTPException(
            status_code=404, detail="No matching queued jobs found."
        )
    return QueueCancelResponse(cancelled_jobs=cancelled)


class CancelResponse(BaseModel):
    detail: str


# Endpoint to cancel the currently running job
@router.post(
    "/cancel",
    summary="Cancel the currently running job",
    status_code=status.HTTP_200_OK,
)
def cancel_current_job() -> CancelResponse:
    cancelled_job_id = job_manager.cancel_running_job()
    if cancelled_job_id is None:
        raise HTTPException(
            status_code=404, detail="No job is currently running."
        )
    return CancelResponse(detail=f"Job {cancelled_job_id} cancelled.")


# Additional endpoints remain unchanged
@router.get(
    "/folders",
    summary="Get the current folder lists",
)
def get_folders(
    conn_args: Dict[str, Any] = Depends(get_db_readonly),
) -> Folders:
    conn = get_database_connection(**conn_args)
    try:
        current_included_folders = get_folders_from_database(
            conn, included=True
        )
        current_excluded_folders = get_folders_from_database(
            conn, included=False
        )
        return Folders(
            included_folders=current_included_folders,
            excluded_folders=current_excluded_folders,
        )
    finally:
        conn.close()


@router.get(
    "/folders/history",
    summary="Get the scan history",
)
def get_scan_history(
    conn_args: Dict[str, Any] = Depends(get_db_readonly),
) -> List[FileScanRecord]:
    conn = get_database_connection(**conn_args)
    try:
        return get_all_file_scans(conn)
    finally:
        conn.close()


@router.get(
    "/data/history",
    summary="Get the extraction history",
)
def get_extraction_history(
    conn_args: Dict[str, Any] = Depends(get_db_readonly),
) -> List[LogRecord]:
    conn = get_database_connection(**conn_args)
    try:
        return get_all_data_logs(conn)
    finally:
        conn.close()


@router.put(
    "/config",
    summary="Update the system configuration",
    status_code=status.HTTP_200_OK,
)
def update_config(
    config: SystemConfig = Body(..., title="The new system configuration"),
    conn_args: Dict[str, Any] = Depends(get_db_readonly),
) -> SystemConfig:
    persist_system_config(conn_args["index_db"], config)
    return retrieve_system_config(conn_args["index_db"])


@router.get(
    "/config",
    summary="Get the current system configuration",
    response_model=SystemConfig,
)
def get_config(
    conn_args: Dict[str, Any] = Depends(get_db_readonly),
) -> SystemConfig:
    return retrieve_system_config(conn_args["index_db"])
