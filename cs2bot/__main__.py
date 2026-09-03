"""`cs2bot` entry point: starts the web control panel."""

from __future__ import annotations

import argparse
import threading
import webbrowser

from .config import load_config, save_config
from .web.app import create_app


def main() -> None:
    parser = argparse.ArgumentParser(prog="cs2bot", description="CS2 chatbot control panel")
    parser.add_argument("--host", default=None, help="bind address (default from config)")
    parser.add_argument("--port", type=int, default=None, help="port (default from config)")
    parser.add_argument(
        "--no-browser", action="store_true", help="do not open the panel in a browser"
    )
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
    # The panel *is* the application, so double-clicking the launcher should land the user in it
    # rather than in front of a console window with a URL to copy.
    host = "127.0.0.1" if config.web.host in {"0.0.0.0", "::"} else config.web.host
    url = f"http://{host}:{config.web.port}"
    if not args.no_browser:
        threading.Timer(1.0, webbrowser.open, args=(url,)).start()
    print(f"CS2 chatbot panel: {url}")
    print("Leave this window open while you play. Close it to stop the bot.")
    uvicorn.run(create_app(engine), host=config.web.host, port=config.web.port, log_level="info")


if __name__ == "__main__":
    main()
