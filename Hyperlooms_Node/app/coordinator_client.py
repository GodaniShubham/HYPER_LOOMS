from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import httpx


class CoordinatorClient:
    def __init__(
        self,
        base_url: str,
        api_token: str,
        timeout: int,
        logger: logging.Logger,
        node_join_token: str = "",
        node_token: str = "",
        tls_verify: bool = True,
        tls_ca_cert_path: str = "",
        tls_client_cert_path: str = "",
        tls_client_key_path: str = "",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._logger = logger
        self._node_join_token = node_join_token.strip()
        self._node_token = node_token.strip()

        verify = self._resolve_verify(tls_verify, tls_ca_cert_path)
        cert = self._resolve_client_cert(tls_client_cert_path, tls_client_key_path)

        headers = {}
        if api_token:
            headers["Authorization"] = f"Bearer {api_token}"
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=self._timeout,
            headers=headers,
            verify=verify,
            cert=cert,
        )

    @property
    def base_url(self) -> str:
        return self._base_url

    async def close(self) -> None:
        await self._client.aclose()

    def set_node_token(self, token: str | None) -> None:
        self._node_token = (token or "").strip()

    def set_node_join_token(self, token: str | None) -> None:
        self._node_join_token = (token or "").strip()

    def _resolve_verify(self, tls_verify: bool, tls_ca_cert_path: str) -> bool | str:
        if not tls_verify:
            return False

        cert_path = tls_ca_cert_path.strip()
        if cert_path and Path(cert_path).exists():
            return cert_path
        if cert_path:
            self._logger.warning("tls_ca_cert_missing", extra={"path": cert_path})
        return True

    def _resolve_client_cert(
        self, tls_client_cert_path: str, tls_client_key_path: str
    ) -> str | tuple[str, str] | None:
        cert_path = tls_client_cert_path.strip()
        key_path = tls_client_key_path.strip()
        if not cert_path:
            return None
        if not Path(cert_path).exists():
            self._logger.warning("tls_client_cert_missing", extra={"path": cert_path})
            return None
        if key_path:
            if not Path(key_path).exists():
                self._logger.warning("tls_client_key_missing", extra={"path": key_path})
                return None
            return (cert_path, key_path)
        return cert_path

    def _node_headers(self) -> dict[str, str] | None:
        if not self._node_token:
            return None
        return {
            "Authorization": f"Bearer {self._node_token}",
            "X-Node-Token": self._node_token,
        }

    def _format_error(self, exc: Exception) -> str:
        if isinstance(exc, httpx.HTTPStatusError):
            response = exc.response
            request = exc.request
            detail = (response.text or "").strip().replace("\n", " ")
            if len(detail) > 220:
                detail = f"{detail[:220]}..."
            return (
                f"status={response.status_code} method={request.method} "
                f"url={request.url} detail={detail}"
            )
        if isinstance(exc, httpx.RequestError):
            request = exc.request
            return (
                f"{exc.__class__.__name__} method={request.method} "
                f"url={request.url} detail={exc}"
            )
        return str(exc)

    async def _request(
        self,
        method: str,
        url: str,
        json_body: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        expected: set[int] | None = None,
        retries: int = 2,
    ) -> httpx.Response:
        if expected is None:
            expected = {200, 201, 202, 204}
        last_exc: Exception | None = None
        for attempt in range(1, retries + 1):
            try:
                response = await self._client.request(method, url, json=json_body, headers=headers)
                if response.status_code in expected:
                    return response
                if response.status_code == 404:
                    return response
                response.raise_for_status()
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if attempt >= retries:
                    self._logger.warning(
                        "coordinator_request_failed method=%s url=%s attempts=%s error=%s",
                        method,
                        url,
                        attempt,
                        self._format_error(exc),
                    )
                    break
                await asyncio.sleep(min(2**attempt, 8))
        message = self._format_error(last_exc) if last_exc else "unknown_error"
        raise RuntimeError(f"coordinator_request_failed: {message}")

    async def get_health(self, endpoint: str) -> bool:
        try:
            response = await self._request("GET", endpoint, expected={200})
            return response.status_code == 200
        except Exception:  # noqa: BLE001
            return False

    async def register_node(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        headers = {"X-Node-Join-Token": self._node_join_token} if self._node_join_token else None
        response = await self._request("POST", endpoint, payload, headers=headers, expected={200, 201})
        if response.status_code == 404:
            self._logger.warning("register_endpoint_missing", extra={"endpoint": endpoint})
            return None
        return response.json()

    async def heartbeat(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        response = await self._request(
            "POST",
            endpoint,
            payload,
            headers=self._node_headers(),
            expected={200, 201},
        )
        if response.status_code == 404:
            self._logger.warning("heartbeat_endpoint_missing", extra={"endpoint": endpoint})
            return None
        return response.json()

    async def claim_job(self, endpoint: str) -> dict[str, Any] | None:
        response = await self._request("GET", endpoint, headers=self._node_headers(), expected={200, 204})
        if response.status_code in {204, 404}:
            return None
        return response.json()

    async def submit_result(self, endpoint: str, payload: dict[str, Any]) -> bool:
        response = await self._request(
            "POST",
            endpoint,
            payload,
            headers=self._node_headers(),
            expected={200, 201, 202},
        )
        return response.status_code in {200, 201, 202}

    async def submit_failure(self, endpoint: str, payload: dict[str, Any]) -> bool:
        response = await self._request(
            "POST",
            endpoint,
            payload,
            headers=self._node_headers(),
            expected={200, 201, 202},
        )
        return response.status_code in {200, 201, 202}

    async def submit_job(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        response = await self._request("POST", endpoint, payload, expected={200, 201, 202})
        if response.status_code in {200, 201, 202}:
            return response.json()
        return None

    async def list_jobs(self, endpoint: str, status_filter: str | None = None) -> list[dict[str, Any]]:
        url = endpoint
        if status_filter:
            separator = "&" if "?" in endpoint else "?"
            url = f"{endpoint}{separator}status={status_filter}"

        response = await self._request("GET", url, headers=self._node_headers(), expected={200})
        data = response.json()
        if isinstance(data, dict) and isinstance(data.get("items"), list):
            return [item for item in data["items"] if isinstance(item, dict)]
        return []
