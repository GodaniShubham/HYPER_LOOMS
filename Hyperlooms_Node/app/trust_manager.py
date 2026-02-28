from __future__ import annotations

import json
from pathlib import Path


class TrustManager:
    def __init__(self, path: Path, default_score: float = 0.9) -> None:
        self._path = path
        self._score = default_score
        self.load()

    @property
    def score(self) -> float:
        return self._score

    def record_success(self, delta: float = 0.01) -> float:
        self._score = min(1.0, self._score + delta)
        self.save()
        return self._score

    def record_failure(self, delta: float = 0.05) -> float:
        self._score = max(0.0, self._score - delta)
        self.save()
        return self._score

    def load(self) -> None:
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and "score" in data:
                self._score = float(data["score"])
        except (json.JSONDecodeError, ValueError):
            return

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"score": round(self._score, 4)}
        self._path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
