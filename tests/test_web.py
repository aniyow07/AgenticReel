"""The local web server: routing, input checks and file serving (no pipeline runs)."""
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

import web
from webapp.voices import voice_label


@pytest.fixture()
def server(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENTREEL_OUTPUT_DIR", str(tmp_path))
    job = tmp_path / "og-20260101-000000-abcdef"
    job.mkdir()
    (job / "state.json").write_text(json.dumps({"job_id": job.name, "status": "completed", "mode": "og",
                                                "topic": "How bees make honey", "stages": {}}), encoding="utf-8")
    (job / "final.mp4").write_bytes(bytes(range(256)) * 4)
    srv = ThreadingHTTPServer(("127.0.0.1", 0), web.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", job
    srv.shutdown()


def call(url, data=None, headers=None, method=None):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def test_lists_jobs_and_details(server):
    base, job = server
    code, _, body = call(base + "/api/jobs")
    rows = json.loads(body)
    assert code == 200 and [r["id"] for r in rows] == [job.name]
    assert rows[0]["has_video"] and rows[0]["versions"] == 1
    code, _, body = call(f"{base}/api/jobs/{job.name}")
    assert code == 200 and json.loads(body)["title"] == "How bees make honey"


def test_rejects_bad_job_ids(server):
    base, _ = server
    for jid in ("..", "..%2F..%2Fwindows", "nope"):
        assert call(f"{base}/api/jobs/{jid}")[0] == 404


def test_video_supports_range_requests(server):
    base, job = server
    code, headers, body = call(f"{base}/api/jobs/{job.name}/video", headers={"Range": "bytes=10-19"})
    assert code == 206 and body == bytes(range(10, 20))
    assert headers["Content-Range"] == "bytes 10-19/1024"


def test_upload_only_accepts_documents(server):
    base, _ = server
    code, _, body = call(base + "/api/upload?name=evil.exe", data=b"MZ", method="POST")
    assert code == 400 and "PDF" in json.loads(body)["errors"][0]
    code, _, body = call(base + "/api/upload?name=notes.txt", data=b"Bees make honey from nectar.", method="POST")
    assert code == 200 and json.loads(body)["name"] == "notes.txt"


def test_brief_errors_are_readable(server):
    base, _ = server
    code, _, body = call(base + "/api/jobs", data=json.dumps({"topic": "x"}).encode(), method="POST",
                         headers={"Content-Type": "application/json"})
    assert code == 400
    assert json.loads(body)["errors"] == ["Write a few words about what the video should explain."]


def test_sources_must_be_server_uploads(server, tmp_path):
    base, _ = server
    outside = tmp_path.parent / "secret.txt"
    code, _, body = call(base + "/api/jobs", method="POST", headers={"Content-Type": "application/json"},
                         data=json.dumps({"topic": "Why the sky is blue", "source_files": [str(outside)]}).encode())
    assert code == 400 and "Attachment not found" in json.loads(body)["errors"][0]


def test_delete_moves_to_trash_and_restore_brings_it_back(server, tmp_path):
    base, job = server
    code, _, body = call(f"{base}/api/jobs/{job.name}/delete", data=b"{}", method="POST")
    assert code == 200 and json.loads(body)["deleted"] == [job.name]
    assert not job.exists() and (tmp_path / "_trash" / job.name / "final.mp4").exists()
    assert json.loads(call(base + "/api/jobs")[2]) == []
    code, _, body = call(base + "/api/restore", data=json.dumps({"ids": [job.name, "../x"]}).encode(), method="POST")
    assert code == 200 and json.loads(body)["restored"] == [job.name] and (job / "state.json").exists()


def test_rename_sets_title_and_download_names(server):
    base, job = server
    code, _, body = call(f"{base}/api/jobs/{job.name}/rename", method="POST",
                         data=json.dumps({"title": 'Bees: how "honey" works?'}).encode())
    assert code == 200 and json.loads(body)["title"] == "Bees how honey works"
    assert json.loads(call(f"{base}/api/jobs/{job.name}")[2])["title"] == "Bees how honey works"
    _, headers, _ = call(f"{base}/api/jobs/{job.name}/video?download")
    assert 'filename="Bees how honey works.mp4"' in headers["Content-Disposition"]
    _, headers, _ = call(f"{base}/api/jobs/{job.name}/video?download&name=" + "%E3%83%9F%E3%83%84%E3%83%90%E3%83%81")
    assert "filename*=UTF-8''%E3%83%9F%E3%83%84%E3%83%90%E3%83%81.mp4" in headers["Content-Disposition"]
    assert "Content-Disposition" not in call(f"{base}/api/jobs/{job.name}/video")[1]


def test_voice_labels_name_the_accent():
    assert voice_label("en-IN-PrabhatNeural") == "Prabhat · Indian accent"
    assert voice_label("ja-JP-KeitaNeural") == "Keita · Japanese accent"
    assert voice_label("en-US-AndrewMultilingualNeural") == "Andrew (multilingual) · American accent"


def test_cross_site_posts_are_refused(server):
    base, _ = server
    code, _, _ = call(base + "/api/jobs", data=b"{}", method="POST", headers={"Origin": "https://evil.example"})
    assert code == 403
