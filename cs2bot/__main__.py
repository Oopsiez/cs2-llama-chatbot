"""`cs2bot` entry point: starts the web control panel."""

from __future__ import annotations

import argparse

from .config import load_config, save_config
from .web.app import create_app


def main() -> None:
    parser = argparse.ArgumentParser(prog="cs2bot", description="CS2 chatbot control panel")
    parser.add_argument("--host", default=None, help="bind address (default from config)")
    parser.add_argument("--port", type=int, default=None, help="port (default from config)")
    args = parser.parse_args()

    import uvicorn

    from .engine import Engine

    config = load_config()
    if args.host:
        config.web.host = args.host
    if args.port:
        config.web.port = args.port
    save_config(config)

    engine = Engine(config)
    print(f"CS2 chatbot panel: http://{config.web.host}:{config.web.port}")
    uvicorn.run(create_app(engine), host=config.web.host, port=config.web.port, log_level="info")


if __name__ == "__main__":
    main()
