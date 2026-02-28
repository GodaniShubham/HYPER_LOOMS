from __future__ import annotations

import asyncio
import base64
import json
import os
import sys
from typing import Any

def _decode_payload() -> dict[str, Any]:
    payload_b64 = os.getenv("JOB_PAYLOAD_B64", "").strip()
    if not payload_b64:
        raise RuntimeError("missing_JOB_PAYLOAD_B64")
    raw = base64.urlsafe_b64decode(payload_b64.encode("ascii"))
    parsed = json.loads(raw.decode("utf-8"))
    if not isinstance(parsed, dict):
        raise RuntimeError("invalid_payload_shape")
    return parsed


async def _run_local_workload(payload: dict[str, Any]) -> dict[str, Any]:
    mode = str(payload.get("mode") or "inference").strip().lower()
    model = str(payload.get("model") or "").strip()
    prompt = str(payload.get("prompt") or "")
    options = payload.get("options") if isinstance(payload.get("options"), dict) else {}
    await asyncio.sleep(0.2)

    max_tokens = int(options.get("max_tokens") or 256)
    temperature = float(options.get("temperature") or 0.2)
    summary = {
        "mode": mode,
        "model": model or "fabric-workload-v1",
        "max_tokens": max_tokens,
        "temperature": temperature,
        "engine": "sandbox-local",
    }
    text = (
        "Container sandbox processed workload locally. "
        f"mode={summary['mode']} model={summary['model']} "
        f"max_tokens={summary['max_tokens']} temperature={summary['temperature']:.2f} "
        f"prompt_len={len(prompt)}."
    )
    return {"response": text, "raw": summary}


async def _main() -> int:
    payload = _decode_payload()
    result = await _run_local_workload(payload)
    sys.stdout.write(json.dumps(result, ensure_ascii=True))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(_main()))
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(str(exc))
        sys.stderr.flush()
        raise
