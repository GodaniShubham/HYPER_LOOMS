from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def _b64decode(raw: str) -> bytes:
    padding = "=" * ((4 - (len(raw) % 4)) % 4)
    return base64.urlsafe_b64decode(f"{raw}{padding}".encode("utf-8"))


class NodeTokenManager:
    def __init__(self, secret: str, ttl_seconds: int = 86_400) -> None:
        self._secret = secret.encode("utf-8")
        self._ttl = max(300, ttl_seconds)

    def issue_token(self, node_id: str) -> tuple[str, datetime]:
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=self._ttl)
        payload = {
            "node_id": node_id,
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
        }
        payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
        signature = hmac.new(self._secret, payload_json, hashlib.sha256).digest()
        token = f"{_b64encode(payload_json)}.{_b64encode(signature)}"
        return token, expires_at

    def verify_token(self, token: str, expected_node_id: str | None = None) -> dict:
        if "." not in token:
            raise ValueError("Malformed node token")
        payload_segment, signature_segment = token.split(".", 1)
        payload_bytes = _b64decode(payload_segment)
        provided_signature = _b64decode(signature_segment)
        expected_signature = hmac.new(self._secret, payload_bytes, hashlib.sha256).digest()
        if not hmac.compare_digest(provided_signature, expected_signature):
            raise ValueError("Invalid node token signature")

        payload = json.loads(payload_bytes.decode("utf-8"))
        exp = int(payload.get("exp", 0))
        node_id = str(payload.get("node_id", ""))
        if not node_id:
            raise ValueError("Invalid node token payload")
        if expected_node_id and expected_node_id != node_id:
            raise ValueError("Node token does not match node path")
        if datetime.now(timezone.utc).timestamp() > exp:
            raise ValueError("Node token expired")
        return payload

