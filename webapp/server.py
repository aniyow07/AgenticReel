"""The HTTP handler: maps URLs to the modules that do the work, and serves files with Range support."""
from __future__ import annotations

import json
import mimetypes
import os
import re
import sys
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from webapp import jobs, library, runner, system, uploads, voices
from webapp.config import MAX_UPLOAD, STATIC, UI_ASSETS, job_dir

# Windows sometimes maps .js to text/plain in the registry; module scripts need the right type.
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/css", ".css")

APP_ROUTES = ("create", "library", "job")  # paths the single-page app handles itself
UI_ASSET_RE = re.compile(r"^(thumb|preview)_(og|minecraft|subway)\.(jpg|mp4)$")


class Handler(BaseHTTPRequestHandler):
    server_version = "AgentReel"

    def log_message(self, fmt, *args):  # quiet: only errors go to the console
        if args and str(args[1] if len(args) > 1 else "").startswith(("4", "5")):
            sys.stderr.write("%s\n" % (fmt % args))

    # ---------- responses ----------
    def send_json(self, obj, code: int = 200):
        body = json.dumps(obj, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, code: int, errors):
        self.send_json({"errors": errors if isinstance(errors, list) else [str(errors)]}, code)

    def body(self) -> bytes:
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_UPLOAD + 1_000_000:
            raise ValueError("Upload is too large")
        return self.rfile.read(n) if n else b""

    def json_body(self) -> dict:
        return json.loads(self.body() or b"{}")

    def send_file(self, p: Path, download_name: str | None = None, cache: bool = False):
        if not p.exists() or not p.is_file():
            return self.send_error_json(404, "Not found")
        size = p.stat().st_size
        ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
        if p.suffix == ".srt":
            ctype = "text/plain; charset=utf-8"
        start, end = 0, size - 1
        rng = self.headers.get("Range")
        partial = False
        if rng and rng.startswith("bytes="):
            a, _, b = rng[6:].split(",")[0].partition("-")
            try:
                if a:
                    start, end = int(a), (int(b) if b else size - 1)
                else:
                    start, end = max(0, size - int(b)), size - 1
                end = min(end, size - 1)
                partial = start <= end
            except ValueError:
                partial = False
            if not partial:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.end_headers()
                return
        self.send_response(206 if partial else 200)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        if partial:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Cache-Control", "max-age=3600" if cache else "no-cache")
        if download_name:
            ascii_name = download_name.encode("ascii", "replace").decode().replace("?", "_").replace('"', "")
            self.send_header("Content-Disposition",
                             f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(download_name)}")
        self.end_headers()
        if self.command == "HEAD":
            return
        with p.open("rb") as f:
            f.seek(start)
            left = end - start + 1
            try:
                while left > 0:
                    chunk = f.read(min(256 * 1024, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)
            except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
                pass

    def _parts(self):
        url = urlparse(self.path)
        return url, [unquote(x) for x in url.path.strip("/").split("/") if x]

    # ---------- GET ----------
    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        url, parts = self._parts()
        try:
            if not parts or parts[0] in APP_ROUTES:
                return self.send_file(STATIC / "index.html")
            if parts[0] == "static" and len(parts) >= 2:
                return self._static(parts[1:])
            if parts[0] == "ui" and len(parts) == 2 and UI_ASSET_RE.match(parts[1]):
                return self.send_file(UI_ASSETS / parts[1], cache=True)
            if parts[0] == "api":
                return self._api_get(url, parts[1:])
            return self.send_error_json(404, "Not found")
        except Exception as e:  # noqa: BLE001
            return self.send_error_json(500, f"{type(e).__name__}: {e}")

    def _static(self, rel: list[str]):
        root = STATIC.resolve()
        p = root.joinpath(*rel).resolve()
        if root not in p.parents:
            return self.send_error_json(404, "Not found")
        return self.send_file(p)

    def _api_get(self, url, parts: list[str]):
        if parts == ["info"]:
            return self.send_json(system.info())
        if parts == ["voices"]:
            return self.send_json(voices.voices())
        if parts == ["jobs"]:
            return self.send_json(jobs.list_all())
        if len(parts) >= 2 and parts[0] == "jobs":
            d = job_dir(parts[1])
            if not d:
                return self.send_error_json(404, "That video was not found.")
            if len(parts) == 2:
                return self.send_json(jobs.detail(d))
            qs = parse_qs(url.query, keep_blank_values=True)
            name = library.download_name(d, (qs.get("name") or [""])[0])
            what = parts[2]
            if what == "video":
                return self.send_file(d / "final.mp4", f"{name}.mp4" if "download" in qs else None)
            if what == "captions":
                return self.send_file(d / "captions.srt", f"{name}.srt")
            if what == "poster":
                p = jobs.poster(d)
                return self.send_file(p, cache=True) if p else self.send_error_json(404, "No poster yet")
        return self.send_error_json(404, "Not found")

    # ---------- POST ----------
    def do_POST(self):
        url, parts = self._parts()
        if self.headers.get("Origin") not in (None, f"http://{self.headers.get('Host')}"):
            return self.send_error_json(403, "Cross-site request refused.")
        try:
            if parts == ["api", "upload"]:
                name = parse_qs(url.query).get("name", ["file"])[0]
                return self.send_json(uploads.save_upload(name, self.body()))
            if parts == ["api", "jobs"]:
                return self.send_json({"id": runner.new_job(self.json_body())})
            if parts == ["api", "restore"]:
                ids = [str(x) for x in self.json_body().get("ids") or []]
                return self.send_json({"restored": library.restore(ids)})
            if len(parts) == 4 and parts[:2] == ["api", "jobs"]:
                return self._job_action(parts[2], parts[3])
            return self.send_error_json(404, "Not found")
        except Exception as e:  # noqa: BLE001
            return self.send_error_json(400, runner.friendly_errors(e))

    def _job_action(self, job_id: str, action: str):
        d = job_dir(job_id)
        if not d:
            return self.send_error_json(404, "That video was not found.")
        if action == "version":
            return self.send_json({"id": runner.new_version(d, self.json_body())})
        if action == "resume":
            return self.send_json({"id": runner.resume(d)})
        if action == "rename":
            return self.send_json({"title": library.rename(d, str(self.json_body().get("title") or ""))})
        if action == "delete":
            return self.send_json({"deleted": library.delete(d, bool(self.json_body().get("all_versions")))})
        if action == "open-folder":
            if os.name == "nt":
                os.startfile(d)  # noqa: S606 - local folder of a job this server owns
            return self.send_json({"ok": True})
        return self.send_error_json(404, "Not found")
