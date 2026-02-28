from __future__ import annotations

import hashlib
import math
import re
from collections import defaultdict

from app.models.job import NodeExecutionResult, VerificationStatus


class ResultVerifier:
    """
    Semantic-majority verifier.
    Uses lightweight hashed embeddings + cosine similarity for Phase-2 reliability.
    """

    def __init__(self, similarity_threshold: float = 0.78, embedding_dims: int = 256) -> None:
        self.similarity_threshold = similarity_threshold
        self.embedding_dims = embedding_dims
        self._word_pattern = re.compile(r"[a-zA-Z0-9_]+")

    def verify(
        self,
        results: list[NodeExecutionResult],
        expected_replicas: int,
    ) -> tuple[VerificationStatus, str | None, float, dict]:
        successful = [result for result in results if result.success and result.output]
        if not successful:
            return VerificationStatus.failed, None, 0.0, {"reason": "no_successful_results"}

        embeddings = {result.node_id: self._embed_text(result.output or "") for result in successful}
        similarity_matrix = self._similarity_matrix(successful, embeddings)
        clusters = self._cluster(successful, embeddings)
        clusters = sorted(clusters, key=lambda group: len(group), reverse=True)

        winner = clusters[0]
        winner_ids = {item.node_id for item in winner}
        winner_size = len(winner)
        winner_output = winner[0].output
        population = max(1, min(expected_replicas, len(successful)))
        majority_required = 1 if population == 1 else ((population // 2) + 1)

        avg_internal_similarity = self._average_internal_similarity(winner, similarity_matrix)
        confidence = max(
            0.0,
            min(
                1.0,
                (winner_size / max(1, len(successful))) * (0.7 + (avg_internal_similarity * 0.3)),
            ),
        )

        if winner_size >= majority_required and avg_internal_similarity >= self.similarity_threshold:
            status = VerificationStatus.verified
        elif winner_size >= majority_required:
            status = VerificationStatus.mismatch
        else:
            status = VerificationStatus.failed

        details = {
            "method": "hashed-embedding-cosine",
            "similarity_threshold": self.similarity_threshold,
            "majority_required": majority_required,
            "majority_nodes": sorted(winner_ids),
            "cluster_sizes": [len(group) for group in clusters],
            "avg_internal_similarity": round(avg_internal_similarity, 4),
            "similarity_matrix": similarity_matrix,
        }
        return status, winner_output, round(confidence, 4), details

    def _embed_text(self, output: str) -> list[float]:
        vector = [0.0] * self.embedding_dims
        tokens = self._word_pattern.findall(output.lower())
        if not tokens:
            return vector

        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
            bucket = int(digest[:8], 16) % self.embedding_dims
            vector[bucket] += 1.0

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]

    def _similarity(self, left: list[float], right: list[float]) -> float:
        dot = sum(a * b for a, b in zip(left, right))
        return max(0.0, min(1.0, dot))

    def _similarity_matrix(
        self, results: list[NodeExecutionResult], embeddings: dict[str, list[float]]
    ) -> dict[str, dict[str, float]]:
        matrix: dict[str, dict[str, float]] = defaultdict(dict)
        for left in results:
            for right in results:
                if right.node_id in matrix[left.node_id]:
                    continue
                similarity = self._similarity(embeddings[left.node_id], embeddings[right.node_id])
                matrix[left.node_id][right.node_id] = round(similarity, 4)
                matrix[right.node_id][left.node_id] = round(similarity, 4)
        return dict(matrix)

    def _cluster(
        self, results: list[NodeExecutionResult], embeddings: dict[str, list[float]]
    ) -> list[list[NodeExecutionResult]]:
        clusters: list[list[NodeExecutionResult]] = []

        for result in results:
            placed = False
            for cluster in clusters:
                centroid = self._cluster_centroid(cluster, embeddings)
                similarity = self._similarity(embeddings[result.node_id], centroid)
                if similarity >= self.similarity_threshold:
                    cluster.append(result)
                    placed = True
                    break
            if not placed:
                clusters.append([result])
        return clusters

    def _cluster_centroid(
        self,
        cluster: list[NodeExecutionResult],
        embeddings: dict[str, list[float]],
    ) -> list[float]:
        if not cluster:
            return [0.0] * self.embedding_dims

        centroid = [0.0] * self.embedding_dims
        for item in cluster:
            embedding = embeddings[item.node_id]
            for index, value in enumerate(embedding):
                centroid[index] += value

        norm = math.sqrt(sum(value * value for value in centroid))
        if norm == 0:
            return centroid
        return [value / norm for value in centroid]

    def _average_internal_similarity(
        self,
        cluster: list[NodeExecutionResult],
        matrix: dict[str, dict[str, float]],
    ) -> float:
        if len(cluster) <= 1:
            return 1.0
        pairs = 0
        total = 0.0
        for left_index in range(len(cluster)):
            for right_index in range(left_index + 1, len(cluster)):
                left = cluster[left_index].node_id
                right = cluster[right_index].node_id
                total += matrix[left][right]
                pairs += 1
        return total / pairs if pairs else 1.0
