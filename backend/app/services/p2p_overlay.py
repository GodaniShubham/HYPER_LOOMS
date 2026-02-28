from __future__ import annotations

import asyncio
import hashlib
from collections import Counter, defaultdict
from datetime import datetime, timezone
from uuid import uuid4

from app.models.p2p import (
    GossipEnvelope,
    JobAssignmentProposal,
    JobConsensusDecision,
    PeerHeartbeatRequest,
    PeerNode,
    PeerRegisterRequest,
    PeerStatus,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class P2POverlayService:
    """
    Phase-4 control plane foundation.
    This runs in-process today, but the same methods can be moved to a real peer daemon.
    """

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._peers: dict[str, PeerNode] = {}
        self._gossip_seq: dict[str, int] = defaultdict(int)
        self._proposals: dict[str, list[JobAssignmentProposal]] = defaultdict(list)

    async def register_peer(self, payload: PeerRegisterRequest) -> PeerNode:
        peer_id = payload.id or f"peer-{uuid4().hex[:10]}"
        now = utc_now()
        async with self._lock:
            existing = self._peers.get(peer_id)
            if existing:
                peer = existing.model_copy(
                    update={
                        "endpoint": payload.endpoint,
                        "region": payload.region,
                        "role": payload.role,
                        "trust_score": payload.trust_score,
                        "load": payload.load,
                        "model_cache": payload.model_cache,
                        "metadata": payload.metadata,
                        "status": PeerStatus.online,
                        "last_seen": now,
                    }
                )
            else:
                peer = PeerNode(
                    id=peer_id,
                    endpoint=payload.endpoint,
                    region=payload.region,
                    role=payload.role,
                    trust_score=payload.trust_score,
                    load=payload.load,
                    model_cache=payload.model_cache,
                    metadata=payload.metadata,
                    status=PeerStatus.online,
                    last_seen=now,
                )
            self._peers[peer_id] = peer
            return peer

    async def heartbeat(self, peer_id: str, payload: PeerHeartbeatRequest) -> PeerNode:
        async with self._lock:
            peer = self._peers.get(peer_id)
            if not peer:
                raise KeyError(f"peer_not_found: {peer_id}")
            update = peer.model_dump()
            if payload.status is not None:
                update["status"] = payload.status
            if payload.trust_score is not None:
                update["trust_score"] = payload.trust_score
            if payload.load is not None:
                update["load"] = payload.load
            if payload.model_cache is not None:
                update["model_cache"] = payload.model_cache
            update["last_seen"] = utc_now()
            next_peer = PeerNode(**update)
            self._peers[peer_id] = next_peer
            return next_peer

    async def list_peers(self) -> list[PeerNode]:
        async with self._lock:
            return sorted(self._peers.values(), key=lambda item: item.id)

    async def ingest_gossip(self, payload: GossipEnvelope) -> int:
        updated = 0
        async with self._lock:
            current_seq = self._gossip_seq[payload.source_peer_id]
            if payload.seq <= current_seq:
                return 0
            self._gossip_seq[payload.source_peer_id] = payload.seq

            for item in payload.membership:
                peer = self._peers.get(item.peer_id)
                if not peer:
                    self._peers[item.peer_id] = PeerNode(
                        id=item.peer_id,
                        status=item.status,
                        trust_score=item.trust_score,
                        load=item.load,
                        region=item.region,
                        last_seen=item.last_seen,
                    )
                    updated += 1
                    continue

                if item.last_seen >= peer.last_seen:
                    self._peers[item.peer_id] = peer.model_copy(
                        update={
                            "status": item.status,
                            "trust_score": item.trust_score,
                            "load": item.load,
                            "region": item.region,
                            "last_seen": item.last_seen,
                        }
                    )
                    updated += 1
        return updated

    async def propose_job_assignment(self, job_id: str, payload: JobAssignmentProposal) -> JobAssignmentProposal:
        proposal = payload.model_copy(update={"job_id": job_id, "created_at": utc_now()})
        async with self._lock:
            self._proposals[job_id] = [
                item
                for item in self._proposals[job_id]
                if item.proposer_peer_id != proposal.proposer_peer_id
            ]
            self._proposals[job_id].append(proposal)
        return proposal

    async def decide_job_assignment(self, job_id: str, replicas: int = 2) -> JobConsensusDecision:
        target = max(1, min(8, replicas))
        async with self._lock:
            peers = [item for item in self._peers.values() if item.status != PeerStatus.offline]
            proposals = list(self._proposals.get(job_id, []))

        if not peers:
            return JobConsensusDecision(job_id=job_id, assigned_node_ids=[], decided_by=[], quorum_size=0, confidence=0.0)

        rendezvous_rank = sorted(peers, key=lambda item: self._rendezvous_score(job_id, item), reverse=True)
        selection = rendezvous_rank[:target]

        votes: Counter[str] = Counter()
        proposers: set[str] = set()
        for proposal in proposals:
            proposers.add(proposal.proposer_peer_id)
            for node_id in proposal.candidate_node_ids:
                votes[node_id] += max(1, int(round(proposal.weight * 2)))
        for node in selection:
            votes[node.id] += 2

        ordered = [node_id for node_id, _ in votes.most_common(max(target * 2, target))]
        fallback = [item.id for item in selection]
        merged: list[str] = []
        for item in [*ordered, *fallback]:
            if item not in merged:
                merged.append(item)
            if len(merged) >= target:
                break

        top_vote = max(votes.values()) if votes else 1
        confidence = 0.0
        if merged:
            confidence = min(1.0, max(0.2, (sum(votes.get(node_id, 1) for node_id in merged) / (top_vote * len(merged) * 1.6))))

        return JobConsensusDecision(
            job_id=job_id,
            assigned_node_ids=merged,
            decided_by=sorted(proposers)[:20],
            quorum_size=len(proposers),
            confidence=round(confidence, 4),
        )

    def _rendezvous_score(self, job_id: str, peer: PeerNode) -> float:
        digest = hashlib.sha256(f"{job_id}:{peer.id}".encode("utf-8")).hexdigest()
        rnd = int(digest[:16], 16) / float(0xFFFFFFFFFFFFFFFF)
        trust = max(0.05, peer.trust_score)
        load_penalty = max(0.1, 1.0 - (peer.load * 0.65))
        return rnd * trust * load_penalty
