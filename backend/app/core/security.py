from fastapi import Header, HTTPException, Request, status

from app.core.config import Settings
from app.services.node_auth import NodeTokenManager


async def require_admin_api_key(
    request: Request, x_api_key: str | None = Header(default=None, alias="X-API-Key")
) -> None:
    settings: Settings = request.app.state.settings
    if not x_api_key or x_api_key != settings.admin_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing admin API key",
        )


def _extract_bearer_token(value: str | None) -> str | None:
    if not value:
        return None
    prefix = "bearer "
    if value.lower().startswith(prefix):
        token = value[len(prefix) :].strip()
        return token or None
    return None


async def require_node_join_token(
    request: Request,
    x_node_join_token: str | None = Header(default=None, alias="X-Node-Join-Token"),
) -> None:
    settings: Settings = request.app.state.settings
    if not settings.node_auth_enabled:
        return
    if not x_node_join_token or x_node_join_token != settings.node_join_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing node join token",
        )


async def require_node_token(
    request: Request,
    node_id: str,
    authorization: str | None = Header(default=None),
    x_node_token: str | None = Header(default=None, alias="X-Node-Token"),
) -> None:
    settings: Settings = request.app.state.settings
    if not settings.node_auth_enabled:
        return

    token = _extract_bearer_token(authorization) or x_node_token
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing node auth token",
        )

    manager: NodeTokenManager = request.app.state.node_token_manager
    try:
        manager.verify_token(token, expected_node_id=node_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid node token: {exc}",
        ) from exc
