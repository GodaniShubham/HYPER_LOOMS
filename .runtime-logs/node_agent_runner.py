from __future__ import annotations

from datetime import datetime
import queue
import signal
import sys
import time

from app.agent import AgentController
from app.config import get_log_dir, load_config, save_config
from app.logger import setup_logging
from app.state import AgentState

TARGET_COORDINATOR = "http://192.168.1.10:8000"


def main() -> int:
    cfg = load_config()
    cfg.coordinator_url = TARGET_COORDINATOR
    if not cfg.node_join_token:
        cfg.node_join_token = "dev-node-join-token"

    if not cfg.consent_accepted:
        cfg.consent_accepted = True
        cfg.consent_name = "AutoRunner"
        cfg.consent_at = datetime.utcnow().isoformat()

    # Keep runtime eligible on systems without dedicated GPU.
    cfg.demo_mode = True

    save_config(cfg)

    events: queue.Queue = queue.Queue()
    state = AgentState()
    logger = setup_logging(get_log_dir(), "INFO")
    controller = AgentController(cfg, state, events, logger)

    controller.start_services()
    time.sleep(2)
    controller.start_runtime()

    print(f"node_agent_started coordinator_url={cfg.coordinator_url} demo_mode={cfg.demo_mode}", flush=True)

    def _shutdown(*_args) -> None:
        print("node_agent_stopping", flush=True)
        try:
            controller.stop_runtime()
            controller.stop_services()
            time.sleep(1)
        finally:
            sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _shutdown)

    while True:
        try:
            event = events.get(timeout=8)
        except queue.Empty:
            print(
                "status_tick "
                f"coord={state.coordinator_status} "
                f"registration={state.registration_status} "
                f"runtime={state.runtime_status} "
                f"node_id={state.node_id or '-'}",
                flush=True,
            )
            continue

        etype = event.get("type", "")
        payload = event.get("payload", {}) or {}

        if etype == "console":
            msg = payload.get("message", "")
            if msg:
                print(msg, flush=True)
        elif etype == "status":
            print(
                "status_update "
                f"coordinator={payload.get('coordinator','')} "
                f"agent={payload.get('agent','')} "
                f"registration={payload.get('registration','')} "
                f"runtime={payload.get('runtime','')} "
                f"node_id={payload.get('node_id','')}",
                flush=True,
            )


if __name__ == "__main__":
    raise SystemExit(main())
