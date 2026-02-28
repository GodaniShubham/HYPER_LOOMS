from __future__ import annotations

import re
from collections.abc import Iterable

from app.models.job import JobConfig
from app.models.node import Node, NodeStatus


class WeightedScheduler:
    """
    Reliability-focused scheduler:
    - filters out offline / under-capacity nodes
    - scores by trust, free VRAM headroom, load, and latency
    """

    MODEL_SIZE_REGEX = re.compile(r"(?P<size>\d+)(?:\.\d+)?b", re.IGNORECASE)
    REGION_RTT_MS: dict[tuple[str, str], int] = {
        ("us-east-1", "us-east-1"): 8,
        ("us-east-1", "us-east-2"): 14,
        ("us-east-1", "us-west-2"): 68,
        ("us-east-1", "eu-west-1"): 84,
        ("us-east-1", "ap-south-1"): 195,
        ("us-west-2", "us-west-2"): 9,
        ("us-west-2", "us-east-1"): 68,
        ("us-west-2", "eu-west-1"): 152,
        ("eu-west-1", "eu-west-1"): 10,
        ("eu-west-1", "us-east-1"): 84,
        ("eu-west-1", "ap-south-1"): 130,
        ("ap-south-1", "ap-south-1"): 12,
        ("ap-south-1", "us-east-1"): 195,
    }

    def select_nodes(self, nodes: list[Node], job_config: JobConfig, replicas: int) -> list[Node]:
        if replicas <= 0:
            return []
        ranked = self.rank_nodes(nodes, job_config)
        return ranked[:replicas]

    def rank_nodes(
        self,
        nodes: Iterable[Node],
        job_config: JobConfig,
        exclude_node_ids: set[str] | None = None,
    ) -> list[Node]:
        exclude = exclude_node_ids or set()
        candidates = [
            node
            for node in nodes
            if node.status != NodeStatus.offline and node.id not in exclude and self._has_capacity(node, job_config)
        ]
        if not candidates:
            return []

        return sorted(
            candidates,
            key=lambda node: self.score_node(node, job_config),
            reverse=True,
        )

    def score_node(self, node: Node, job_config: JobConfig) -> float:
        availability = 1.0 if node.status == NodeStatus.healthy else 0.65
        trust = node.trust_score
        vram_score = self._free_vram_ratio(node, job_config)
        load_headroom = max(0.0, 1.0 - min(1.0, node.jobs_running / 6))
        latency_score = self._latency_score(node.latency_ms_avg)
        region_score = self._region_affinity_score(node.region, job_config.preferred_region)
        model_cache_score = self._model_cache_score(node, job_config)

        return (
            (availability * 0.14)
            + (trust * 0.28)
            + (vram_score * 0.22)
            + (load_headroom * 0.11)
            + (latency_score * 0.07)
            + (region_score * 0.10)
            + (model_cache_score * 0.08)
        )

    def estimate_required_vram_gb(self, job_config: JobConfig) -> float:
        model_name = job_config.model.lower()
        match = self.MODEL_SIZE_REGEX.search(model_name)
        parameter_hint_b = float(match.group("size")) if match else 13.0
        token_factor = min(2.0, max(0.4, job_config.max_tokens / 2048))
        required = (parameter_hint_b * 0.7) * token_factor
        return max(4.0, min(80.0, round(required, 2)))

    def _has_capacity(self, node: Node, job_config: JobConfig) -> bool:
        required = self.estimate_required_vram_gb(job_config)
        if node.vram_total_gb < required * 0.75:
            return False
        return node.free_vram_gb >= max(2.0, required * 0.3)

    def _free_vram_ratio(self, node: Node, job_config: JobConfig) -> float:
        required = self.estimate_required_vram_gb(job_config)
        if node.vram_total_gb <= 0:
            return 0.0
        headroom = max(0.0, node.free_vram_gb - (required * 0.2))
        return min(1.0, headroom / node.vram_total_gb)

    def _latency_score(self, latency_ms: float) -> float:
        if latency_ms <= 0:
            return 0.75
        if latency_ms >= 1600:
            return 0.1
        return max(0.1, 1.0 - (latency_ms / 1700))

    def _region_affinity_score(self, node_region: str, preferred_region: str | None) -> float:
        if not preferred_region:
            return 0.7
        left = (preferred_region or "").strip().lower()
        right = (node_region or "").strip().lower()
        if not left or not right:
            return 0.45
        if left == right:
            return 1.0
        rtt = self.REGION_RTT_MS.get((left, right), self.REGION_RTT_MS.get((right, left), 220))
        return max(0.15, min(1.0, 1.0 - (rtt / 280)))

    def _model_cache_score(self, node: Node, job_config: JobConfig) -> float:
        model = job_config.model.strip().lower()
        if not model:
            return 0.4
        cached = {item.strip().lower() for item in node.model_cache}
        if model in cached:
            return 1.0
        family = model.split(":")[0].split("-")[0]
        if any(item.startswith(family) for item in cached):
            return 0.72
        return 0.25
