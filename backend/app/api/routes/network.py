from fastapi import APIRouter, Depends

from app.api.deps import get_store
from app.schemas.network import NetworkSnapshot, NetworkStats
from app.services.state_store import InMemoryStateStore

router = APIRouter(prefix="/network", tags=["network"])


@router.get("/stats", response_model=NetworkStats)
async def network_stats(store: InMemoryStateStore = Depends(get_store)) -> NetworkStats:
    return await store.network_stats()


@router.get("/snapshot", response_model=NetworkSnapshot)
async def network_snapshot(store: InMemoryStateStore = Depends(get_store)) -> NetworkSnapshot:
    return await store.network_snapshot()

