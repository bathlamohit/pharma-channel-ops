"""New claims: an append-only JSONL file, one event per line (ADR 0013).

    data/claims_store.jsonl        (path from CLAIMS_STORE; gitignored like the audit log)

Every claim that arrives after the data extract is registered here with a claim number in the
register's format, CLM-yymm-nnnnn (C&F procedure Sch 2 2.6.1). Nothing is edited or deleted:
a claim's current state is its events read in order. The checks read these claims next to
the cleaned register, so a second claim on the same batch is caught (CO-POL-014 5.5, 5.6).

This module is the only code that knows claims live in a file. A hosted database later
replaces this file and nothing else.

Limits: one server. On Vercel the disk does not last, so new claims would be lost there.
"""
import copy
import fcntl
import json
import os
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from agent import policy

PATH = Path(os.getenv("CLAIMS_STORE", Path(__file__).resolve().parent.parent / "data" / "claims_store.jsonl"))

STATUSES = ("Received", "Awaiting info", "Verified", "On hold", "Approved", "Rejected", "Credit note raised", "Closed")
OPEN = ("Received", "Awaiting info", "Verified", "On hold")
# Allowed moves. Approval needs the physical verification first (CO-POL-014 5.6).
NEXT = {
    "Received": ("Awaiting info", "Verified", "On hold", "Rejected"),
    "Awaiting info": ("Received", "Verified", "On hold", "Rejected"),
    "Verified": ("Approved", "Rejected", "On hold"),
    "On hold": ("Received", "Verified", "Approved", "Rejected"),
    "Approved": ("Credit note raised",),
    "Credit note raised": ("Closed",),
    "Rejected": ("Closed",),
    "Closed": (),
}
DECISION_STATUS = {"approve": "Approved", "reject": "Rejected", "hold": "On hold"}


class StoreError(ValueError):
    """A move the claim's current status does not allow."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def _locked():
    """One writer at a time on this server; the lock covers read-then-append."""
    PATH.parent.mkdir(parents=True, exist_ok=True)
    with PATH.open("a+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            f.seek(0)
            yield f
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def _read(f=None) -> list[dict]:
    if f is None:
        if not PATH.exists():
            return []
        with PATH.open() as fh:
            fcntl.flock(fh, fcntl.LOCK_SH)  # never read half of a registration (QA D-03)
            try:
                return _read(fh)
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)
    out = []
    for n, line in enumerate(f, 1):
        if line.strip():
            rec = json.loads(line)
            rec["line"] = n
            out.append(rec)
    return out


def _append(f, *recs: dict) -> dict:
    """Write one or more events in a single write, so a reader sees all of them or none."""
    f.seek(0, os.SEEK_END)
    f.write("".join(json.dumps(r, default=str) + "\n" for r in recs))
    f.flush()
    return recs[-1]


def _register_serial_max() -> int:
    from agent import tools  # the cleaned register; imported here to keep this module light
    return int(tools.table("expiry_claims.csv")["claim_no"].str[-5:].astype(int).max())


def _next_serial(events: list[dict]) -> int:
    used = [int(e["claim_no"][-5:]) for e in events if e["event"] == "registered"]
    return max([_register_serial_max(), *used]) + 1


def register(lines: list[dict], *, source: str, intake_ref: str, by: str, intake: dict | None = None) -> list[str]:
    """Give each claim line a claim number and log it as Received (or Awaiting info when a
    record or input was missing). `lines` are LineResults from the graph."""
    numbers = []
    with _locked() as f:
        events = _read(f)
        serial = _next_serial(events)
        for ln in lines:
            c = ln["claim"]
            claimed_on = str(c.get("claim_date") or date.today().isoformat())[:10]
            claim_no = f"CLM-{claimed_on[2:4]}{claimed_on[5:7]}-{serial:05d}"
            serial += 1
            fields = {k: c.get(k) for k in ("stockist_code", "batch_no", "sku_code", "sku_text", "qty_claimed",
                                            "claim_type", "invoice_ref", "expiry_date_as_claimed")}
            first = "Awaiting info" if ln["route"] == "needs_person" else "Received"
            _append(f,
                    {"event": "registered", "claim_no": claim_no, "at": _now(), "by": by, "source": source,
                     "intake_ref": intake_ref, "claim_date": claimed_on, **fields, "intake": intake},
                    {"event": "checked", "claim_no": claim_no, "at": _now(), "route": ln["route"],
                     "recommendation": ln.get("recommendation"), "checks": ln.get("checks"),
                     "errors": ln.get("errors"), "audit_id": ln.get("audit_id")},
                    {"event": "status", "claim_no": claim_no, "at": _now(), "status": first, "by": "system",
                     "note": "logged on arrival (CF Sch 2 2.6.1)"})
            numbers.append(claim_no)
    return numbers


def _working_days_after(start: date, n: int) -> date:
    d, left = start, n
    while left:
        d += timedelta(days=1)
        if d.weekday() < 5:  # Mon-Fri; no holiday calendar yet
            left -= 1
    return d


_CACHE: dict = {}


def _version() -> tuple:
    """The file's size and modification time: every append changes the size (QA D-04)."""
    try:
        st = PATH.stat()
        return str(PATH), st.st_size, st.st_mtime_ns
    except OSError:
        return str(PATH), 0, 0


def claims(today: date | None = None) -> list[dict]:
    """Current state of every stored claim, newest first, with its history and due dates.
    Replayed once per version of the file, then served from memory as copies."""
    return copy.deepcopy(snapshot(today))


def snapshot(today: date | None = None) -> list[dict]:
    """The cached list itself, READ-ONLY: for serialising and lookups that never change it.
    Replays the file only when it has changed."""
    today = today or date.today()
    key = (_version(), today)
    if _CACHE.get("key") != key:
        _CACHE.update(key=key, value=_replay(today))
    return _CACHE["value"]


_shared = snapshot


def _replay(today: date) -> list[dict]:
    by_no: dict[str, dict] = {}
    for e in _read():
        no = e["claim_no"]
        if e["event"] == "registered":
            by_no[no] = {**{k: v for k, v in e.items() if k not in ("event", "line", "at")},
                         "received_at": e["at"], "lines": [e["line"]], "history": []}
            continue
        c = by_no.get(no)
        if c is None:
            continue
        c["lines"].append(e["line"])
        if e["event"] == "checked":
            c.update(route=e["route"], recommendation=e["recommendation"], checks=e["checks"],
                     errors=e["errors"], audit_id=e.get("audit_id"))
        elif e["event"] == "status":
            c["status"] = e["status"]
            if e.get("credit_note_no"):
                c["credit_note_no"] = e["credit_note_no"]
            c["history"].append({k: e.get(k) for k in ("at", "status", "by", "note", "credit_note_no")})
        elif e["event"] == "decision":
            c["history"].append({"at": e["at"], "status": f"Decision: {e['decision']}", "by": e["by"],
                                 "note": e.get("note"), "override": e.get("override")})
    out = []
    for c in by_no.values():
        if "status" not in c:  # a registration without its status event: never shown half-written
            continue
        received = date.fromisoformat(c["claim_date"])
        verify_by = _working_days_after(received, int(policy.CLAIM_VERIFY_WORKING_DAYS.value))
        credit_by = received + timedelta(days=int(policy.CLAIM_SETTLE_DAYS.value))
        verified = any(h["status"] in ("Verified", "Approved", "Credit note raised") for h in c["history"])
        c["due"] = {
            "verify_by": verify_by.isoformat(), "credit_by": credit_by.isoformat(),
            "verify_overdue": not verified and c["status"] in OPEN and today > verify_by,
            "credit_overdue": c["status"] in (*OPEN, "Approved") and today > credit_by,
            "days_open": (today - received).days,
        }
        out.append(c)
    return sorted(out, key=lambda c: c["received_at"], reverse=True)


def get(claim_no: str) -> dict | None:
    hit = next((c for c in snapshot() if c["claim_no"] == claim_no), None)
    return copy.deepcopy(hit) if hit else None


def move(claim_no: str, status: str, by: str, note: str = "", credit_note_no: str | None = None) -> dict:
    """Change a claim's status, if its current status allows it."""
    by = (by or "").strip()
    if len(by) < 2:
        raise StoreError("Give the name of the person moving the claim")
    with _locked() as f:
        current = None
        for e in _read(f):
            if e["claim_no"] == claim_no and e["event"] == "status":
                current = e["status"]
        if current is None:
            raise StoreError(f"{claim_no} is not a new claim in the store")
        if status not in NEXT[current]:
            allowed = ", ".join(NEXT[current]) or "nothing (closed)"
            raise StoreError(f"{claim_no} is {current}; it can move to {allowed}")
        if status == "Credit note raised" and not (credit_note_no or "").strip():
            raise StoreError("Give the credit note number")
        return _append(f, {"event": "status", "claim_no": claim_no, "at": _now(), "status": status, "by": by,
                           "note": note, "credit_note_no": (credit_note_no or "").strip() or None})


def decide(claim_no: str, decision: str, by: str, note: str, override: bool) -> dict:
    """A person's decision on one stored claim: logged, then the status follows it."""
    status = DECISION_STATUS[decision]
    moved = move(claim_no, status, by, note)
    with _locked() as f:
        _append(f, {"event": "decision", "claim_no": claim_no, "at": _now(), "decision": decision, "by": by,
                    "note": note, "override": override})
    return moved


def as_register_rows(stockist_code: str, batch_no: str | None = None) -> list[dict]:  # noqa: D401
    """Stored claims shaped like register rows, for the duplicate and quantity checks.
    Register status: Rejected stays Rejected, a credit note means Credited, else Pending."""
    rows = []
    for c in _shared():
        if c.get("stockist_code") != stockist_code or (batch_no and c.get("batch_no") != batch_no):
            continue
        settled = "Rejected" if c["status"] == "Rejected" or (
            c["status"] == "Closed" and any(h["status"] == "Rejected" for h in c["history"])) else \
            "Credited" if c.get("credit_note_no") else "Pending"
        rows.append({"claim_no": c["claim_no"], "claim_date": c["claim_date"], "stockist_code": c["stockist_code"],
                     "batch_no": c["batch_no"], "qty_claimed": c["qty_claimed"], "status": settled,
                     "src_line": c["lines"][0]})
    return rows
