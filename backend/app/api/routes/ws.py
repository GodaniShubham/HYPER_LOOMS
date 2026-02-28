from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["ws"])


@router.websocket("/ws/jobs/{job_id}")
async def ws_job_stream(websocket: WebSocket, job_id: str) -> None:
    hub = websocket.app.state.ws_hub
    store = websocket.app.state.store

    await hub.connect_job(job_id, websocket)
    snapshot = await store.get_job(job_id)
    if snapshot:
        await websocket.send_json({"type": "job_snapshot", "job": snapshot.model_dump(mode="json")})

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await hub.disconnect_job(job_id, websocket)


@router.websocket("/ws/network")
async def ws_network_stream(websocket: WebSocket) -> None:
    hub = websocket.app.state.ws_hub
    store = websocket.app.state.store

    await hub.connect_network(websocket)
    await websocket.send_json(
        {
            "type": "network_snapshot",
            "nodes": [node.model_dump(mode="json") for node in await store.list_nodes()],
            "stats": await store.network_stats(),
        }
    )
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await hub.disconnect_network(websocket)

