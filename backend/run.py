from __future__ import annotations

import uvicorn

from app.core.config import get_settings


def main() -> None:
    settings = get_settings()
    kwargs = {
        "host": "0.0.0.0",
        "port": 8000,
        "reload": False,
    }
    if settings.tls_cert_file and settings.tls_key_file:
        kwargs["ssl_certfile"] = settings.tls_cert_file
        kwargs["ssl_keyfile"] = settings.tls_key_file
    uvicorn.run("app.main:app", **kwargs)


if __name__ == "__main__":
    main()
