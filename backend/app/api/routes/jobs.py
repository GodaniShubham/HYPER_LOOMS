from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_orchestrator, get_store
from app.models.job import Job, JobCreateRequest, JobListResponse, JobStatus
from app.services.orchestrator import JobOrchestrator
from app.services.state_store import InMemoryStateStore

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("", response_model=Job, status_code=status.HTTP_202_ACCEPTED)
async def submit_job(
    payload: JobCreateRequest,
    orchestrator: JobOrchestrator = Depends(get_orchestrator),
) -> Job:
    try:
        return await orchestrator.submit_job(payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=str(exc)) from exc


@router.get("/{job_id}", response_model=Job)
async def get_job(job_id: str, store: InMemoryStateStore = Depends(get_store)) -> Job:
    job = await store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


@router.get("", response_model=JobListResponse)
async def list_jobs(
    status_filter: JobStatus | None = Query(default=None, alias="status"),
    store: InMemoryStateStore = Depends(get_store),
) -> JobListResponse:
    jobs = await store.list_jobs()
    if status_filter:
        jobs = [job for job in jobs if job.status == status_filter]
    return JobListResponse(items=jobs)


@router.post("/{job_id}/retry", response_model=Job, status_code=status.HTTP_202_ACCEPTED)
async def retry_job(
    job_id: str,
    orchestrator: JobOrchestrator = Depends(get_orchestrator),
) -> Job:
    try:
        return await orchestrator.retry_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=str(exc)) from exc
