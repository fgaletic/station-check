"""Production entry point: the app plus the Source mock in one process.

Hosting platforms give one public port ($PORT). The app serves the API and the built
frontend there, and the Source mock runs privately on localhost:8787, where the app
sends to it, until real Source credentials replace it (set SOURCE_API_URL etc.).

    python serve.py
"""
import os
import threading
from http.server import ThreadingHTTPServer

import uvicorn

from mock_source import server as mock


def start_mock():
    mock.load_state()
    httpd = ThreadingHTTPServer(("127.0.0.1", mock.PORT), mock.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()


if __name__ == "__main__":
    if "SOURCE_API_URL" not in os.environ:
        start_mock()
    uvicorn.run("backend.app.main:app", host="0.0.0.0", port=int(os.environ.get("PORT", "8000")),
                proxy_headers=True, forwarded_allow_ips="*")
