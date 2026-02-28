from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PeerStatus(StrEnum):
    online = "online"
    suspect = "suspect"
    offline = "offline"


class PeerRole(StrEnum):
    worker = "worker"
    validator = "validator"
    router = "router"


class PeerNode(BaseModel):
    id: str = Field(default_factory=lambda: f"peer-{uuid4().hex[:10]}")
    endpoint: str = Field(default="", max_length=300)
    region: str = Field(default="local", min_length=2, max_length=64)
    role: PeerRole = PeerRole.worker
    status: PeerStatus = PeerStatus.online
    trust_score: float = Field(default=0.9, ge=0, le=1)
    load: float = Field(default=0, ge=0, le=1)
    model_cache: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    last_seen: datetime = Field(default_factory=utc_now)
    created_at: datetime = Field(default_factory=utc_now)


class PeerRegisterRequest(BaseModel):
    id: str | None = None
    endpoint: str = Field(default="", max_length=300)
    region: str = Field(default="local", min_length=2, max_length=64)
    role: PeerRole = PeerRole.worker
    trust_score: float = Field(default=0.9, ge=0, le=1)
    load: float = Field(default=0, ge=0, le=1)
    model_cache: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PeerHeartbeatRequest(BaseModel):
    status: PeerStatus | None = None
    trust_score: float | None = Field(default=None, ge=0, le=1)
    load: float | None = Field(default=None, ge=0, le=1)
    model_cache: list[str] | None = None


class GossipMembershipEntry(BaseModel):
    peer_id: str
    status: PeerStatus
    trust_score: float = Field(ge=0, le=1)
    load: float = Field(ge=0, le=1)
    last_seen: datetime
    region: str = "local"


class GossipEnvelope(BaseModel):
    source_peer_id: str
    seq: int = Field(default=0, ge=0)
    sent_at: datetime = Field(default_factory=utc_now)
    membership: list[GossipMembershipEntry] = Field(default_factory=list)


class JobAssignmentProposal(BaseModel):
    job_id: str
    proposer_peer_id: str
    candidate_node_ids: list[str] = Field(default_factory=list)
    weight: float = Field(default=1.0, ge=0)
    reason: str = "proposal"
    created_at: datetime = Field(default_factory=utc_now)


class JobConsensusDecision(BaseModel):
    job_id: str
    assigned_node_ids: list[str] = Field(default_factory=list)
    decided_by: list[str] = Field(default_factory=list)
    quorum_size: int = Field(default=0, ge=0)
    method: str = "rendezvous-hash+majority-proposal"
    confidence: float = Field(default=0, ge=0, le=1)
    created_at: datetime = Field(default_factory=utc_now)


class PeerListResponse(BaseModel):
    items: list[PeerNode]
