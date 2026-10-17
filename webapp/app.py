"""Command-line entry point: parse flags, start the server, open the browser."""
from __future__ import annotations

import argparse
import os
import threading
import webbrowser
from http.server import ThreadingHTTPServer

from webapp.config import settings
from webapp.server import Handler
from webapp.jobs import warm_posters


def main() -> int:
    ap = argparse.ArgumentParser(description="AgentReel web app")
    ap.add_argument("--provider", choices=["openrouter", "gemini"])
    ap.add_argument("--gemini-interval", type=float, metavar="SECONDS")
    ap.add_argument("--port", type=int, default=8600)
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    if a.provider:
        os.environ["LLM_PROVIDER"] = a.provider
    if a.gemini_interval is not None:
        os.environ["GEMINI_MIN_INTERVAL_S"] = str(a.gemini_interval)
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    srv.daemon_threads = True
    url = f"http://127.0.0.1:{a.port}/"
    print(f"AgentReel is running at {url}  (AI: {settings().llm_provider}). Press Ctrl+C to stop.", flush=True)
    if not a.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    threading.Thread(target=warm_posters, daemon=True).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0
