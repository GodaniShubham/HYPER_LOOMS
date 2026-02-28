# ComputeFabric Node

A Windows GPU node agent that turns a machine into a ComputeFabric worker.

## Features
- GPU + VRAM detection (PyTorch)
- RAM detection (psutil)
- Coordinator registration + heartbeat with node auth tokens
- TLS-capable coordinator communication (CA + client cert support)
- Job polling + distributed workload execution (fabric mode)
- Optional containerized sandbox execution for jobs
- Trust score tracking
- Rotating logs
- Rich UI (status, logs, settings, workload model)
- Windows packaging via PyInstaller

## Folder Structure
```text
Hyperlooms_Node/
  app/
    agent.py
    container_runner.py
    config.py
    coordinator_client.py
    gpu_detector.py
    heartbeat.py
    job_worker.py
    logger.py
    main.py
    models.py
    state.py
    trust_manager.py
    ui/
      app.py
  sandbox/
    Dockerfile
    runner.py
  installer/
    ComputeFabricNode.iss
  requirements.txt
```

## Run Locally
```bash
cd Hyperlooms_Node
python -m venv .venv
. .venv/Scripts/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m app.main
```

### Optional: Build Sandbox Runtime Image
```bash
cd Hyperlooms_Node/sandbox
docker build -t computefabric-node-sandbox:latest .
```

## Config Location
`%APPDATA%/ComputeFabric/config.json`

Example:
```json
{
  "coordinator_url": "http://localhost:8000",
  "api_token": "",
  "node_join_token": "dev-node-join-token",
  "node_auth_token": "",
  "tls_verify": true,
  "tls_ca_cert_path": "",
  "tls_client_cert_path": "",
  "tls_client_key_path": "",
  "model_name": "fabric-workload-v1",
  "provider_hint": "fabric",
  "execution_mode": "local",
  "container_image": "computefabric-node-sandbox:latest",
  "container_timeout_sec": 180,
  "container_cpus": 4.0,
  "container_memory_mb": 8192,
  "container_enable_gpu": true,
  "container_network": "bridge",
  "container_readonly_rootfs": true,
  "container_pids_limit": 256,
  "container_no_new_privileges": true,
  "container_fallback_to_local": true,
  "auto_download_models": false,
  "node_id": "node-...",
  "region": "local",
  "heartbeat_interval_sec": 10,
  "job_poll_interval_sec": 3,
  "request_timeout_sec": 15,
  "register_endpoint": "/api/v1/nodes/register",
  "heartbeat_endpoint": "/api/v1/nodes/{node_id}/heartbeat",
  "job_claim_endpoint": "/api/v1/nodes/{node_id}/jobs/next",
  "job_result_endpoint": "/api/v1/nodes/{node_id}/jobs/{job_id}/result",
  "job_fail_endpoint": "/api/v1/nodes/{node_id}/jobs/{job_id}/fail"
}
```

## Build .exe (PyInstaller)
```bash
pip install pyinstaller
pyinstaller --onefile --noconsole --name ComputeFabricNode app/main.py
```
Output will be in `dist/ComputeFabricNode.exe`.

## Installer (Inno Setup)
1. Install Inno Setup.
2. Build the exe with PyInstaller.
3. Open `installer/ComputeFabricNode.iss` and compile.

## Notes
- If job endpoints are not implemented on the Coordinator yet, the node will register + heartbeat but will idle for jobs.
- For `execution_mode=container`, build the sandbox image first and ensure Docker is installed/running.
- For secure coordinator mode, set `node_join_token` and keep `node_auth_token` managed by registration flow.


## Multi-PC Coordinator

If the backend runs on another machine, set `coordinator_url` to that machine's LAN/public IP (for example `http://192.168.1.20:8000`).
Using `localhost` on a second PC will fail to register because it points to that PC itself.
