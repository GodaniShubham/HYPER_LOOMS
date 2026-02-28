from fastapi import APIRouter, Depends, Request, status

from app.api.deps import get_hub, get_store
from app.core.security import require_admin_api_key
from app.models.node import NodeHeartbeatRequest, NodeListResponse, NodeRegisterRequest, NodeRegisterResponse, NodeStatus
from app.schemas.admin import AdminLiveJobsResponse, NodeJobDistributionResponse
from app.schemas.network import JobStatusCount
from app.services.state_store import InMemoryStateStore
from app.ws.hub import WebSocketHub

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin_api_key)])


@router.get("/nodes", response_model=NodeListResponse)
async def admin_nodes(store: InMemoryStateStore = Depends(get_store)) -> NodeListResponse:
    return NodeListResponse(items=await store.list_nodes())


@router.get("/jobs/distribution", response_model=NodeJobDistributionResponse)
async def jobs_distribution(store: InMemoryStateStore = Depends(get_store)) -> NodeJobDistributionResponse:
    return await store.jobs_distribution()


@router.get("/jobs/status-counts", response_model=list[JobStatusCount])
async def jobs_status_counts(store: InMemoryStateStore = Depends(get_store)) -> list[JobStatusCount]:
    counts = await store.jobs_status_counts()
    return [JobStatusCount(status=status, count=count) for status, count in counts.items()]


@router.get("/jobs/live", response_model=AdminLiveJobsResponse)
async def live_jobs(store: InMemoryStateStore = Depends(get_store)) -> AdminLiveJobsResponse:
    return await store.admin_live_jobs()


@router.post("/nodes/register-local", response_model=NodeRegisterResponse, status_code=status.HTTP_201_CREATED)
async def register_local_node(
    request: Request,
    payload: NodeRegisterRequest,
    store: InMemoryStateStore = Depends(get_store),
    hub: WebSocketHub = Depends(get_hub),
) -> NodeRegisterResponse:
    node = await store.register_node(payload)
    node = await store.heartbeat(
        node.id,
        NodeHeartbeatRequest(
            status=NodeStatus.healthy,
            jobs_running=0,
            vram_used_gb=0,
            model_cache=payload.model_cache,
        ),
    )
    node_token = None
    token_expires_at = None
    settings = request.app.state.settings
    if settings.node_auth_enabled:
        manager = request.app.state.node_token_manager
        node_token, token_expires_at = manager.issue_token(node.id)

    snapshot = await store.network_snapshot()
    await hub.broadcast_network({"event": "network_update", "snapshot": snapshot.model_dump(mode="json")})
    return NodeRegisterResponse(node=node, node_token=node_token, token_expires_at=token_expires_at)
