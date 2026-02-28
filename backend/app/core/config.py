from functools import lru_cache
import json

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "ComputeFabric Orchestrator"
    api_v1_prefix: str = "/api/v1"
    log_level: str = "INFO"

    redis_url: str = "redis://redis:6379/0"
    admin_api_key: str = "dev-admin-key"
    cors_origins: str = "http://localhost:3000"

    node_heartbeat_timeout_sec: int = 30
    network_broadcast_interval_sec: int = 3
    job_claim_timeout_sec: int = 90
    verification_similarity_threshold: float = 0.78
    seed_demo_nodes: bool = False
    node_auth_enabled: bool = True
    node_join_token: str = "dev-node-join-token"
    node_token_secret: str = "dev-node-token-secret"
    node_token_ttl_sec: int = 86_400
    job_assignment_hash_secret: str = "dev-job-assignment-hash-secret"
    job_assignment_hash_ttl_sec: int = 900
    enforce_https: bool = False
    allow_insecure_localhost: bool = True
    tls_cert_file: str | None = None
    tls_key_file: str | None = None
    bootstrap_user_credits: float = 5000.0
    metadata_db_url: str = "sqlite:///./.tmp/computefabric_metadata.db"
    training_credit_per_gpu_hour: float = 14.0
    training_tick_interval_sec: int = 3
    enable_single_node_test_fallback: bool = True

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: str | list[str] | None) -> str:
        if value is None:
            return "http://localhost:3000"
        if isinstance(value, list):
            return ",".join(str(item).strip() for item in value if str(item).strip())
        return str(value).strip()

    @property
    def cors_origins_list(self) -> list[str]:
        value = (self.cors_origins or "").strip()
        if not value:
            return ["http://localhost:3000"]
        if value.startswith("["):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed if str(item).strip()]
            except json.JSONDecodeError:
                pass
        return [item.strip() for item in value.split(",") if item.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
