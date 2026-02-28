from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
import json
import os
from pathlib import Path


APP_NAME = "ComputeFabric"
CONFIG_FILENAME = "config.json"
TRUST_FILENAME = "trust.json"


def get_app_dir() -> Path:
    base = os.getenv("APPDATA") or str(Path.home())
    return Path(base) / APP_NAME


def get_log_dir() -> Path:
    return get_app_dir() / "logs"


def get_config_path() -> Path:
    return get_app_dir() / CONFIG_FILENAME


def get_trust_path() -> Path:
    return get_app_dir() / TRUST_FILENAME


@dataclass
class AgentConfig:
    coordinator_url: str = "http://127.0.0.1:8000"
    api_token: str = ""
    node_join_token: str = "dev-node-join-token"
    node_auth_token: str = ""
    node_auth_token_expires_at: str = ""

    tls_verify: bool = True
    tls_ca_cert_path: str = ""
    tls_client_cert_path: str = ""
    tls_client_key_path: str = ""

    model_name: str = "fabric-workload-v1"
    provider_hint: str = "fabric"
    auto_download_models: bool = False
    model_cache: list[str] = field(default_factory=list)

    execution_mode: str = "local"  # local|container
    container_image: str = "computefabric-node-sandbox:latest"
    container_timeout_sec: int = 180
    container_cpus: float = 4.0
    container_memory_mb: int = 8192
    container_enable_gpu: bool = True
    container_network: str = "bridge"
    container_readonly_rootfs: bool = True
    container_pids_limit: int = 256
    container_no_new_privileges: bool = True
    container_fallback_to_local: bool = True

    node_id: str | None = None
    region: str = "local"

    heartbeat_interval_sec: int = 10
    job_poll_interval_sec: int = 3
    request_timeout_sec: int = 15

    register_endpoint: str = "/api/v1/nodes/register"
    heartbeat_endpoint: str = "/api/v1/nodes/{node_id}/heartbeat"
    job_claim_endpoint: str = "/api/v1/nodes/{node_id}/jobs/next"
    job_result_endpoint: str = "/api/v1/nodes/{node_id}/jobs/{job_id}/result"
    job_fail_endpoint: str = "/api/v1/nodes/{node_id}/jobs/{job_id}/fail"
    job_submit_endpoint: str = "/api/v1/jobs"
    health_endpoint: str = "/healthz"

    consent_accepted: bool = False
    consent_name: str = ""
    consent_at: str = ""

    demo_mode: bool = False
    require_gpu: bool = True
    min_vram_gb: float = 0.5
    min_ram_gb: float = 2.0
    min_disk_gb: float = 20.0


def ensure_dirs() -> None:
    get_app_dir().mkdir(parents=True, exist_ok=True)
    get_log_dir().mkdir(parents=True, exist_ok=True)


def _normalize_model_cache(models: list[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for item in models:
        cleaned = str(item).strip()
        if not cleaned:
            continue
        lowered = cleaned.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        unique.append(cleaned)
    return unique[-32:]


def _is_legacy_openai_model(name: str) -> bool:
    lowered = str(name).strip().lower()
    return lowered.startswith("gpt-") or lowered.startswith("o1") or lowered.startswith("o3")


def load_config() -> AgentConfig:
    ensure_dirs()
    config_path = get_config_path()
    cfg = AgentConfig()
    if not config_path.exists():
        save_config(cfg)
        return cfg

    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        backup = config_path.with_suffix(".invalid.json")
        config_path.replace(backup)
        save_config(cfg)
        return cfg

    known_fields = {field.name for field in fields(cfg)}
    for field in fields(cfg):
        if field.name in data:
            setattr(cfg, field.name, data[field.name])

    # Runtime now uses fabric-local execution; keep persisted configs aligned.
    changed = False
    if any(key not in known_fields for key in data.keys()):
        changed = True

    cfg.provider_hint = "fabric"
    if data.get("provider_hint") != "fabric":
        changed = True

    cfg.auto_download_models = False
    if data.get("auto_download_models") is not False:
        changed = True

    if not str(cfg.model_name).strip():
        cfg.model_name = "fabric-workload-v1"
        changed = True
    elif _is_legacy_openai_model(cfg.model_name):
        cfg.model_name = "fabric-workload-v1"
        changed = True

    cache_candidates = [cfg.model_name, *cfg.model_cache]
    cache_candidates = [item for item in cache_candidates if not _is_legacy_openai_model(item)]
    cfg.model_cache = _normalize_model_cache(cache_candidates)
    if cfg.model_cache != data.get("model_cache"):
        changed = True

    # Persist one-time migration to drop legacy provider keys from disk config.
    if changed:
        save_config(cfg)

    return cfg


def save_config(cfg: AgentConfig) -> None:
    ensure_dirs()
    get_config_path().write_text(
        json.dumps(asdict(cfg), indent=2, sort_keys=True),
        encoding="utf-8",
    )
