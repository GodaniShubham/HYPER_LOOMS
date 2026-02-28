import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import sys

from fastapi import Depends, FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse, JSONResponse

from app.api.deps import get_hub, get_store
from app.api.routes import admin_router, credits_router, jobs_router, network_router, nodes_router, p2p_router, training_router
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.models.credits import CreditAccountType
from app.models.job import Job
from app.services.credit_ledger import CreditLedger
from app.services.orchestrator import JobOrchestrator
from app.services.node_auth import NodeTokenManager
from app.services.p2p_overlay import P2POverlayService
from app.services.scheduler import WeightedScheduler
from app.services.state_store import InMemoryStateStore
from app.services.training_metadata_store import TrainingMetadataStore
from app.services.training_orchestrator import TrainingOrchestrator
from app.services.verifier import ResultVerifier
from app.ws.hub import WebSocketHub

logger = get_logger("computefabric.main")

if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


async def network_publisher(app: FastAPI) -> None:
    settings = app.state.settings
    loop = asyncio.get_running_loop()
    last_training_tick = 0.0
    while True:
        if settings.seed_demo_nodes:
            await app.state.store.synthetic_pulse()
        affected_jobs = await app.state.store.expire_stale_job_claims(settings.job_claim_timeout_sec)
        affected_jobs |= await app.state.store.expire_stale_nodes(settings.node_heartbeat_timeout_sec)
        for job_id in affected_jobs:
            job = await app.state.store.get_job(job_id)
            if job:
                await app.state.ws_hub.broadcast_job(job_id, {"event": "job_update", "job": job.model_dump(mode="json")})

        now = loop.time()
        if now - last_training_tick >= settings.training_tick_interval_sec:
            last_training_tick = now
            app.state.training_orchestrator.tick_training_runs()

        snapshot = await app.state.store.network_snapshot()
        await app.state.ws_hub.broadcast_network({"event": "network_update", "snapshot": snapshot.model_dump(mode="json")})
        await asyncio.sleep(settings.network_broadcast_interval_sec)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)

    scheduler = WeightedScheduler()
    verifier = ResultVerifier(similarity_threshold=settings.verification_similarity_threshold)
    credit_ledger = CreditLedger(bootstrap_user_credits=settings.bootstrap_user_credits)
    # Platform reserve starts with runway for node rewards in local/dev mode.
    await credit_ledger.mint(
        account_type=CreditAccountType.platform,
        account_id=credit_ledger.PLATFORM_ACCOUNT_ID,
        amount=max(100_000.0, settings.bootstrap_user_credits * 10),
        reason="bootstrap_platform_reserve",
        idempotency_key="bootstrap:platform-reserve",
    )

    store = InMemoryStateStore(
        scheduler=scheduler,
        verifier=verifier,
        credits=credit_ledger,
        assignment_hash_secret=settings.job_assignment_hash_secret,
        assignment_hash_ttl_sec=settings.job_assignment_hash_ttl_sec,
        enable_single_node_test_fallback=settings.enable_single_node_test_fallback,
    )
    if settings.seed_demo_nodes:
        await store.seed_nodes()
    ws_hub = WebSocketHub()
    orchestrator = JobOrchestrator(store, scheduler, verifier, ws_hub, credits=credit_ledger)
    p2p_overlay = P2POverlayService()
    training_metadata_store = TrainingMetadataStore(settings.metadata_db_url)
    training_metadata_store.init()
    training_orchestrator = TrainingOrchestrator(
        metadata_store=training_metadata_store,
        scheduler=scheduler,
        state_store=store,
        credits=credit_ledger,
        credit_per_gpu_hour=settings.training_credit_per_gpu_hour,
    )

    app.state.settings = settings
    app.state.store = store
    app.state.ws_hub = ws_hub
    app.state.orchestrator = orchestrator
    app.state.credit_ledger = credit_ledger
    app.state.p2p_overlay = p2p_overlay
    app.state.training_metadata_store = training_metadata_store
    app.state.training_orchestrator = training_orchestrator
    app.state.node_token_manager = NodeTokenManager(
        secret=settings.node_token_secret,
        ttl_seconds=settings.node_token_ttl_sec,
    )

    app.state.network_task = asyncio.create_task(network_publisher(app))
    logger.info("service_started", extra={"event": "service.started"})

    try:
        yield
    finally:
        app.state.network_task.cancel()
        try:
            await app.state.network_task
        except asyncio.CancelledError:
            pass
        logger.info("service_stopped", extra={"event": "service.stopped"})


settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    default_response_class=ORJSONResponse,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def https_enforcement(request: Request, call_next):
    if not settings.enforce_https:
        return await call_next(request)

    proto = request.headers.get("x-forwarded-proto", request.url.scheme or "")
    client_host = request.client.host if request.client else ""
    is_local = client_host in {"127.0.0.1", "::1", "localhost"}
    if proto.lower() != "https" and not (settings.allow_insecure_localhost and is_local):
        return JSONResponse(
            status_code=426,
            content={"detail": "HTTPS is required for this endpoint"},
        )
    return await call_next(request)

app.include_router(nodes_router, prefix=settings.api_v1_prefix)
app.include_router(jobs_router, prefix=settings.api_v1_prefix)
app.include_router(network_router, prefix=settings.api_v1_prefix)
app.include_router(admin_router, prefix=settings.api_v1_prefix)
app.include_router(credits_router, prefix=settings.api_v1_prefix)
app.include_router(p2p_router, prefix=settings.api_v1_prefix)
app.include_router(training_router, prefix=settings.api_v1_prefix)


@app.get("/healthz")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.websocket("/ws/jobs/{job_id}")
async def job_updates(
    websocket: WebSocket,
    job_id: str,
    store: InMemoryStateStore = Depends(get_store),
    hub: WebSocketHub = Depends(get_hub),
) -> None:
    await hub.connect_job(job_id, websocket)
    job: Job | None = await store.get_job(job_id)
    if job:
        await websocket.send_json({"event": "job_update", "job": job.model_dump(mode="json")})
    try:
        while True:
            # Keep socket alive and allow ping/pong frames from clients.
            await websocket.receive_text()
    except WebSocketDisconnect:
        await hub.disconnect_job(job_id, websocket)


@app.websocket("/ws/network")
async def network_updates(
    websocket: WebSocket,
    store: InMemoryStateStore = Depends(get_store),
    hub: WebSocketHub = Depends(get_hub),
) -> None:
    await hub.connect_network(websocket)
    snapshot = await store.network_snapshot()
    await websocket.send_json({"event": "network_update", "snapshot": snapshot.model_dump(mode="json")})
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        await hub.disconnect_network(websocket)


