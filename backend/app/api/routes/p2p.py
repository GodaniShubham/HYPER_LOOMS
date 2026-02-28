from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.deps import get_p2p_overlay
from app.models.p2p import (
    GossipEnvelope,
    JobAssignmentProposal,
    JobConsensusDecision,
    PeerHeartbeatRequest,
    PeerListResponse,
    PeerNode,
    PeerRegisterRequest,
)
from app.services.p2p_overlay import P2POverlayService

router = APIRouter(prefix="/p2p", tags=["p2p"])


@router.post("/peers/register", response_model=PeerNode, status_code=status.HTTP_201_CREATED)
async def register_peer(
    payload: PeerRegisterRequest,
    overlay: P2POverlayService = Depends(get_p2p_overlay),
) -> PeerNode:
    return await overlay.register_peer(payload)


@router.post("/peers/{peer_id}/heartbeat", response_model=PeerNode)
async def peer_heartbeat(
    peer_id: str,
    payload: PeerHeartbeatRequest,
    overlay: P2POverlayService = Depends(get_p2p_overlay),
) -> PeerNode:
    try:
        return await overlay.heartbeat(peer_id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/peers", response_model=PeerListResponse)
async def list_peers(
    overlay: P2POverlayService = Depends(get_p2p_overlay),
) -> PeerListResponse:
    return PeerListResponse(items=await overlay.list_peers())


@router.post("/gossip")
async def ingest_gossip(
    payload: GossipEnvelope,
    overlay: P2POverlayService = Depends(get_p2p_overlay),
) -> dict:
    updated = await overlay.ingest_gossip(payload)
    return {"updated_peers": updated}


@router.post("/jobs/{job_id}/proposals", response_model=JobAssignmentProposal)
async def propose_job(
    job_id: str,
    payload: JobAssignmentProposal,
    overlay: P2POverlayService = Depends(get_p2p_overlay),
) -> JobAssignmentProposal:
    return await overlay.propose_job_assignment(job_id, payload)


@router.get("/jobs/{job_id}/decision", response_model=JobConsensusDecision)
async def decide_job(
    job_id: str,
    replicas: int = Query(default=2, ge=1, le=8),
    overlay: P2POverlayService = Depends(get_p2p_overlay),
) -> JobConsensusDecision:
    return await overlay.decide_job_assignment(job_id, replicas=replicas)
