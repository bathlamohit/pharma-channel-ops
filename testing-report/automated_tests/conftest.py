"""Shared fixtures for the QA suite in testing-report/automated_tests.

- Every test gets empty, temporary stores (claims, stock actions, audit log): real files in data/
  are never read for state or written.
- The model key is removed, so no test can call the model or spend money.
- `api` is a TestClient that logs every request and response to evidence/api_calls.jsonl.
- `server` starts a real uvicorn process on a free port (for concurrency, performance and the
  browser tests), with its own temporary stores and no model key.
- Each test's docstring starts "TC-ID | type | requirement | description"; the outcome of every
  test is written to evidence/results.jsonl, which builds Test_Cases.xlsx.
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "testing-report"
EVIDENCE = REPORT / "evidence"
DATA = REPORT / "test_data"
sys.path.insert(0, str(ROOT))
os.environ.pop("OPENROUTER_API_KEY", None)
EVIDENCE.mkdir(exist_ok=True)
(EVIDENCE / "screenshots").mkdir(exist_ok=True)


def load(name: str):
    return json.loads((DATA / name).read_text())


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    from agent import audit, stock_log, store
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setattr(store, "PATH", tmp_path / "claims_store.jsonl")
    monkeypatch.setattr(stock_log, "PATH", tmp_path / "stock_actions.jsonl")
    monkeypatch.setattr(audit, "LOG", tmp_path / "audit_log.jsonl")
    import agent.claim_nodes as nodes

    def no_model():
        raise AssertionError("the model was called during a QA test")
    monkeypatch.setattr(nodes, "get_llm", no_model)
    yield


class LoggedClient:
    """TestClient wrapper that keeps request/response evidence."""

    def __init__(self, client, test_id: str):
        self.c, self.test_id = client, test_id

    def _log(self, method, url, body, r):
        with (EVIDENCE / "api_calls.jsonl").open("a") as f:
            f.write(json.dumps({"test": self.test_id, "method": method, "url": url,
                                "request": (json.dumps(body)[:400] if body is not None else None),
                                "status": r.status_code, "response": r.text[:400],
                                "ms": round(r.elapsed.total_seconds() * 1000, 1) if hasattr(r, "elapsed") else None}) + "\n")

    def get(self, url, **kw):
        r = self.c.get(url, **kw)
        self._log("GET", url, None, r)
        return r

    def post(self, url, json=None, **kw):
        r = self.c.post(url, json=json, **kw)
        self._log("POST", url, json, r)
        return r


@pytest.fixture
def api(request):
    from fastapi.testclient import TestClient

    from app import app
    return LoggedClient(TestClient(app), request.node.nodeid)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def server():
    """A real server process with its own temporary stores and no model key."""
    tmp = Path(tempfile.mkdtemp(prefix="sankalp-qa-server-"))
    port = _free_port()
    env = {**os.environ, "CLAIMS_STORE": str(tmp / "claims.jsonl"), "STOCK_ACTIONS": str(tmp / "actions.jsonl"),
           "AUDIT_LOG": str(tmp / "audit.jsonl"), "OPENROUTER_API_KEY": ""}
    started = time.time()
    proc = subprocess.Popen([str(ROOT / ".venv" / "bin" / "uvicorn"), "app:app", "--port", str(port), "--log-level", "warning"],
                            cwd=ROOT, env=env, stdout=(tmp / "server.log").open("w"), stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            if httpx.get(base + "/api/health", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.2)
    boot = time.time() - started
    yield {"base": base, "tmp": tmp, "boot_seconds": round(boot, 2)}
    proc.terminate()
    proc.wait(timeout=10)


# --- results capture --------------------------------------------------------------------
def pytest_runtest_logreport(report):
    if report.when != "call" and not (report.when == "setup" and report.outcome != "passed"):
        return
    doc = getattr(report, "_doc", "") or ""
    parts = [p.strip() for p in doc.split("|")] + ["", "", "", ""]
    with (EVIDENCE / "results.jsonl").open("a") as f:
        f.write(json.dumps({"nodeid": report.nodeid, "tc_id": parts[0], "type": parts[1], "requirement": parts[2],
                            "description": parts[3], "outcome": "xfailed" if hasattr(report, "wasxfail") and report.skipped
                            else report.outcome, "seconds": round(report.duration, 3),
                            "message": (str(report.longrepr)[-600:] if report.failed else
                                        getattr(report, "wasxfail", "") or "")}) + "\n")


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    doc = (item.function.__doc__ or "").strip().splitlines()
    rep._doc = doc[0] if doc else item.name
    if rep.when == "call" and rep.failed and "page" in item.funcargs:
        try:
            item.funcargs["page"].screenshot(path=str(EVIDENCE / "screenshots" / f"FAIL-{item.name}.png"), full_page=True)
        except Exception:  # noqa: BLE001
            pass


def pytest_sessionstart(session):
    for f in ("results.jsonl", "api_calls.jsonl"):
        p = EVIDENCE / f
        if p.exists() and not os.environ.get("QA_APPEND"):
            p.unlink()
