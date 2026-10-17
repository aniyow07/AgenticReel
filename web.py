"""AgentReel web app: a local server for the browser UI in webui/.

    python web.py                         # provider from .env (LLM_PROVIDER), opens the browser
    python web.py --provider gemini       # or openrouter
    python web.py --port 8600 --no-browser

The server code lives in the webapp/ package and the browser code in webui/. Only standard-library HTTP
is used; the server listens on 127.0.0.1 and runs the same pipeline as run.py and the Streamlit app.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from webapp.app import main  # noqa: E402
from webapp.server import Handler  # noqa: E402,F401 - re-exported for tests and embedding

if __name__ == "__main__":
    sys.exit(main())
