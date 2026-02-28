# Hyperlooms

Programmable distributed compute for AI workloads.

Hyperlooms is a startup-grade distributed AI compute platform built as a clean monolith:
- `frontend`: Next.js + TypeScript + Tailwind operator UI.
- `backend`: FastAPI async orchestrator with websockets.
- Redis/Postgres-ready contracts with phase-1 in-memory execution.

## Monorepo Layout

```text
.
|-- backend
|   |-- app
|   |   |-- api
|   |   |-- core
|   |   |-- db
|   |   |-- models
|   |   |-- schemas
|   |   |-- services
|   |   |-- ws
|   |   `-- main.py
|   |-- .env.example
|   |-- Dockerfile
|   `-- requirements.txt
|-- frontend
|   |-- app
|   |-- components
|   |-- hooks
|   |-- modules
|   |-- services
|   |-- store
|   |-- types
|   |-- .env.example
|   |-- Dockerfile
|   `-- package.json
`-- docker-compose.yml
```

## Product Surfaces

- `/`: Control landing page with live network stats and CTA.
- `/jobs`: User job console with prompt editor, config, live logs, and status flow.
- `/jobs/[jobId]`: Result viewer with merged output and per-node diff.
- `/admin`: Admin dashboard with node table, trust, and jobs-per-node chart.

## Orchestrator API

- `POST /api/v1/nodes/register`
- `POST /api/v1/nodes/{node_id}/heartbeat`
- `GET /api/v1/nodes`
- `GET /api/v1/nodes/{node_id}/jobs/next`
- `POST /api/v1/nodes/{node_id}/jobs/{job_id}/result`
- `POST /api/v1/nodes/{node_id}/jobs/{job_id}/fail`
- `POST /api/v1/jobs`
- `GET /api/v1/jobs/{job_id}`
- `GET /api/v1/jobs`
- `POST /api/v1/jobs/{job_id}/retry`
- `GET /api/v1/network/stats`
- `GET /api/v1/network/snapshot`
- `GET /api/v1/admin/nodes` (`X-API-Key`)
- `GET /api/v1/admin/jobs/distribution` (`X-API-Key`)
- `GET /api/v1/admin/jobs/status-counts` (`X-API-Key`)
- `GET /api/v1/admin/jobs/live` (`X-API-Key`)
- `GET /api/v1/credits/accounts/{account_type}/{account_id}`
- `GET /api/v1/credits/transactions/list`
- `POST /api/v1/credits/mint` (`X-API-Key`)
- `POST /api/v1/credits/spend`
- `POST /api/v1/credits/reward` (`X-API-Key`)
- `POST /api/v1/credits/transfer` (`X-API-Key`)
- `POST /api/v1/p2p/peers/register`
- `POST /api/v1/p2p/peers/{peer_id}/heartbeat`
- `POST /api/v1/p2p/gossip`
- `POST /api/v1/p2p/jobs/{job_id}/proposals`
- `GET /api/v1/p2p/jobs/{job_id}/decision`
- `WS /ws/jobs/{job_id}`
- `WS /ws/network`

## Execution Flow

1. User submits prompt to orchestrator (`pending` queue).
2. Real node agents poll `/nodes/{node_id}/jobs/next` and claim jobs.
3. Node agent executes inference locally (Ollama/OpenAI provider mode).
4. Node submits `/result` or `/fail` for that job.
5. Coordinator updates trust, node runtime stats, and live websocket streams.
6. Frontend/admin views reflect real node/job state dynamically.

## Reliability Upgrades (Phase 2)

- Smart scheduler scoring by trust, free VRAM, load, and latency.
- Multi-replica job verification with semantic similarity (hashed embedding cosine).
- Majority-based merge + confidence scoring.
- Heartbeat timeout handling with automatic replica reassignment.
- Claim lease expiry handling for stuck nodes.

## Security + Scale Upgrades (Phase 3)

- Node join-token authentication for registration.
- Per-node signed bearer token auth for heartbeat/job claim/result/fail APIs.
- Optional HTTPS enforcement (`ENFORCE_HTTPS=true`) with local bypass toggle.
- TLS-ready backend run mode (`python run.py`) using `TLS_CERT_FILE` + `TLS_KEY_FILE`.
- Region-aware + model-cache-aware scheduling.
- Container sandbox execution path for node agents (`execution_mode=container`) with CPU/memory/GPU/pids limits.

## Decentralization Vision (Phase 4)

- P2P orchestration primitives shipped under `/api/v1/p2p/*` (gossip, proposals, deterministic decisioning).
- Credit ledger + settlement APIs under `/api/v1/credits/*`.
- Automatic charge/reward/refund integrated with job lifecycle.
- Full roadmap and architecture: `docs/phase4-decentralization.md`.

## Local Run

### Option A: Docker Compose

```bash
docker compose up --build
```

- Frontend: `http://localhost:3000`
- Backend: `http://localhost:8000`
- OpenAPI: `http://localhost:8000/docs`

### Option B: Manual

Backend:

```bash
cd backend
python -m venv .venv
. .venv/Scripts/activate
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Secure backend runtime (TLS env-driven):

```bash
cd backend
python run.py
```

Frontend:

```bash
cd frontend
npm install
copy .env.example .env.local
npm run dev
```

Node Agent (separate process):

```bash
cd ComputeFabric_Node
python -m venv .venv
. .venv/Scripts/activate
pip install -r requirements.txt
python -m app.main
```

Optional container sandbox image for node execution:

```bash
cd Hyperlooms_Node/sandbox
docker build -t hyperlooms-node-sandbox:latest .
```



## Multi-PC Node Setup

1. Run backend on a reachable host/IP (example: `http://192.168.1.20:8000`).
2. On each Node Agent machine, set `Coordinator URL` to that host/IP in Settings (not `localhost`).
3. Ensure firewall allows inbound `8000/tcp` on the backend host.
4. Start node services, accept consent, register node, then start runtime.
