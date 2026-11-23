"""Audit log: every path ends here, and every human decision is appended to it.

The graph stops at a recommendation. The person's approve/reject arrives as a second
request (POST /api/decision), because Vercel keeps no process between requests.

Locally the log is a JSONL file. On Vercel the disk does not last.
TODO (open decision, "Where is the audit log kept?"): a small hosted store; until then
each decision is also returned for download.
"""
import fcntl
import json
import os
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from agent.state import SankalpState

LOG = Path(os.getenv("AUDIT_LOG", Path(__file__).resolve().parent.parent / "data" / "audit_log.jsonl"))


def _append(record: dict) -> dict:
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a") as f:
            f.write(json.dumps(record, default=str) + "\n")
    except OSError:  # read-only disk (Vercel): the caller still gets the record to download
        record["stored"] = False
    return record


def audit_log(state: SankalpState) -> dict:
    audit_id = uuid.uuid4().hex[:12]
    _append({"type": "recommendation", "audit_id": audit_id, "at": datetime.now(timezone.utc).isoformat(),
             "entry": state.get("entry"), "source": (state.get("raw_input") or {}).get("email_id"),
             "route": state.get("route"), "lines": state.get("lines"), "status_facts": state.get("status_facts"), "errors": state.get("errors"), "citations": state.get("citations")})
    return {"audit_id": audit_id}


@contextmanager
def decision_lock():
    """One decision at a time on this server, so 'already decided?' and the write are atomic
    (QA D-02). Where the disk is read-only (Vercel) there is no log and nothing to lock."""
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        fh = open(LOG.with_suffix(".lock"), "a")
    except OSError:
        yield
        return
    with fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def log_kept() -> bool:
    """True when this server keeps its log (locally). On Vercel nothing is kept, so nothing can be looked up."""
    return LOG.exists()


def _records():
    try:
        with LOG.open() as f:
            for line in f:
                yield json.loads(line)
    except (OSError, ValueError):
        return


def subject_of(rec: dict) -> str | None:
    """What a decision is about: the register claim number, or the email the lines came from.
    Checking the same claim again gives a new audit id but the same subject."""
    if rec.get("entry") == "register":
        lines = rec.get("lines") or []
        return (lines[0].get("claim") or {}).get("claim_no") if lines else None
    if rec.get("entry") == "email" and rec.get("source"):
        return f"email:{rec['source']}"
    return None


def decisions_on(subject: str) -> list[dict]:
    """Earlier decisions on the same claim or email, under any audit id."""
    return [r for r in _records() if r.get("type") == "decision" and r.get("subject") == subject]


def find_recommendation(audit_id: str) -> dict | None:
    """The logged recommendation for an audit id, if this server kept it (not on Vercel)."""
    try:
        with LOG.open() as f:
            for line in f:
                rec = json.loads(line)
                if rec.get("type") == "recommendation" and rec.get("audit_id") == audit_id:
                    return rec
    except (OSError, ValueError):
        return None
    return None


def record_decision(audit_id: str, decided_by: str, decision: str, note: str = "",
                    recommended: str | None = None, override: bool = False, subject: str | None = None,
                    changes: dict | None = None) -> dict:
    return _append({"type": "decision", "audit_id": audit_id, "subject": subject, "decided_by": decided_by,
                    "decision": decision, "recommended": recommended, "override": override, "note": note,
                    "changes": changes, "at": datetime.now(timezone.utc).isoformat()})
