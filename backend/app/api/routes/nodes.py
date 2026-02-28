from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.api.deps import get_hub, get_store
from app.core.security import require_node_join_token, require_node_token
from app.models.job import Job, JobFailureSubmitRequest, JobResultSubmitRequest, NodeJobClaimResponse
from app.models.node import Node, NodeHeartbeatRequest, NodeListResponse, NodeRegisterRequest, NodeRegisterResponse
from app.services.state_store import InMemoryStateStore
from app.ws.hub import WebSocketHub

router = APIRouter(prefix="/nodes", tags=["nodes"])


@router.post(
    "/register",
    response_model=NodeRegisterResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_node_join_token)],
)
async def register_node(
    request: Request,
    payload: NodeRegisterRequest,
    store: InMemoryStateStore = Depends(get_store),
    hub: WebSocketHub = Depends(get_hub),
) -> NodeRegisterResponse:
    node = await store.register_node(payload)
    settings = request.app.state.settings
    node_token = None
    token_expires_at = None
    if settings.node_auth_enabled:
        manager = request.app.state.node_token_manager
        node_token, token_expires_at = manager.issue_token(node.id)
    snapshot = await store.network_snapshot()
    await hub.broadcast_network({"event": "network_update", "snapshot": snapshot.model_dump(mode="json")})
    return NodeRegisterResponse(node=node, node_token=node_token, token_expires_at=token_expires_at)


@router.post("/{node_id}/heartbeat", response_model=Node)
async def node_heartbeat(
    node_id: str,
    payload: NodeHeartbeatRequest,
    _: None = Depends(require_node_token),
    store: InMemoryStateStore = Depends(get_store),
    hub: WebSocketHub = Depends(get_hub),
) -> Node:
    try:
        node = await store.heartbeat(node_id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    snapshot = await store.network_snapshot()
    await hub.broadcast_network({"event": "network_update", "snapshot": snapshot.model_dump(mode="json")})
    return node


@router.get("", response_model=NodeListResponse)
async def list_nodes(store: InMemoryStateStore = Depends(get_store)) -> NodeListResponse:
    return NodeListResponse(items=await store.list_nodes())


@router.get("/{node_id}/jobs/next", response_model=NodeJobClaimResponse | None)
async def claim_next_job(
    node_id: str,
    _: None = Depends(require_node_token),
    store: InMemoryStateStore = Depends(get_store),
    hub: WebSocketHub = Depends(get_hub),
) -> NodeJobClaimResponse | Response:
    try:
        claim = await store.claim_next_job(node_id)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    if claim is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    job, assignment_hash_key, assignment_expires_at = claim

    await hub.broadcast_job(job.id, {"event": "job_update", "job": job.model_dump(mode="json")})
    snapshot = await store.network_snapshot()
    await hub.broadcast_network({"event": "network_update", "snapshot": snapshot.model_dump(mode="json")})
    return NodeJobClaimResponse(
        job=job,
        assignment_hash_key=assignment_hash_key,
        assignment_expires_at=assignment_expires_at,
    )


@router.post("/{node_id}/jobs/{job_id}/result", response_model=Job)
async def submit_job_result(
    node_id: str,
    job_id: str,
    payload: JobResultSubmitRequest,
    _: None = Depends(require_node_token),
    store: InMemoryStateStore = Depends(get_store),
    hub: WebSocketHub = Depends(get_hub),
) -> Job:
    try:
        job = await store.submit_job_result(
            node_id=node_id,
            job_id=job_id,
            output=payload.output,
            latency_ms=payload.latency_ms,
            assignment_hash_key=payload.assignment_hash_key,
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    await hub.broadcast_job(job.id, {"event": "job_update", "job": job.model_dump(mode="json")})
    snapshot = await store.network_snapshot()
    await hub.broadcast_network({"event": "network_update", "snapshot": snapshot.model_dump(mode="json")})
    return job


@router.post("/{node_id}/jobs/{job_id}/fail", response_model=Job)
async def submit_job_failure(
    node_id: str,
    job_id: str,
    payload: JobFailureSubmitRequest,
    _: None = Depends(require_node_token),
    store: InMemoryStateStore = Depends(get_store),
    hub: WebSocketHub = Depends(get_hub),
) -> Job:
    try:
        job = await store.submit_job_failure(
            node_id=node_id,
            job_id=job_id,
            error=payload.error,
            assignment_hash_key=payload.assignment_hash_key,
        )
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    await hub.broadcast_job(job.id, {"event": "job_update", "job": job.model_dump(mode="json")})
    snapshot = await store.network_snapshot()
    await hub.broadcast_network({"event": "network_update", "snapshot": snapshot.model_dump(mode="json")})
    return job
