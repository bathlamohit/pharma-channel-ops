"""What people did about the stock plan: an append-only JSONL file, like the claims store (ADR 0014).

    data/stock_actions.jsonl     (path from STOCK_ACTIONS; gitignored)

The plan (agent/stock.py) says what should happen; this records who did it and when. A CDC
return must be requested before it is approved, and approved before it is received
(CF Sch 2 2.5). Nothing is edited or deleted.
"""
import fcntl
import json
import os
from datetime import datetime, timezone
from pathlib import Path

PATH = Path(os.getenv("STOCK_ACTIONS", Path(__file__).resolve().parent.parent / "data" / "stock_actions.jsonl"))

STEPS = {
    "Blocked in SAP": None,                    # block: restricted stock, CO-POL-014 7.2
    "Added to destruction list": "Blocked in SAP",
    "Offered with stockist consent": None,     # short-dated, 7.1
    "Return requested": None,                  # CDC return, CF Sch 2 2.5 (Regional Distribution Manager)
    "Return approved": "Return requested",     # Head of Supply Chain
    "Received at CDC": "Return approved",
    "Pushed in dispatch": None,
    "Picking order confirmed": None,           # FEFO, CF 6.3
    "Raised with CFA": None,                   # batch-order alert
    "Checked with CFA": None,                  # not-moving watch list (plan step 3)
    "Stockist agreed": None,                   # short-dated dispatch: consent on record (CO-POL-014 7.1)
    "No agreement on record": None,            # short-dated dispatch: breach confirmed
    # Allocation (ADR 0015)
    "Allocation raised": None,                 # refill a short CFA from the CDC
    "Dispatched from CDC": "Allocation raised",
    "Replenishment paused": None,              # excess: stop sending more
    "Share change requested": None,            # mid-year share change via the RDM (CF Sch 2 2.2)
    "Share change approved": "Share change requested",
    "Raised with NSM": None,                   # scheme report, CO-POL-014 4.3
    "Raised with CFO": None,
}


# Steps that may recur for the same CFA (a new pick order each week; raising the alert again).
REPEATABLE = {"Picking order confirmed", "Raised with CFA"}
SCHEME_STEPS = {"Raised with NSM", "Raised with CFO", "Share change requested", "Share change approved"}  # national steps


class StepError(ValueError):
    pass


def _key(r: dict) -> tuple:
    """A step is done once per CFA, product, batch and note (the note names the other CFA of a move)."""
    return r["cnf_code"], r.get("sku_code"), r.get("batch_no"), r["step"], r.get("note") or ""


def _read() -> list[dict]:
    if not PATH.exists():
        return []
    with PATH.open() as f:
        return [json.loads(line) for line in f if line.strip()]


def actions(cfa: str | None = None) -> list[dict]:
    rows = _read()
    return [r for r in rows if cfa is None or r["cnf_code"] == cfa]


def record(cnf_code: str, step: str, by: str, sku_code: str | None = None, batch_no: str | None = None,
           qty: int | None = None, note: str = "") -> dict:
    if step not in STEPS:
        raise StepError(f"Unknown step {step!r}")
    by = (by or "").strip()
    if len(by) < 2:
        raise StepError("Give the name of the person who did it")
    PATH.parent.mkdir(parents=True, exist_ok=True)
    with PATH.open("a+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            f.seek(0)
            done = [json.loads(line) for line in f if line.strip()]
            rec_key = (cnf_code, sku_code, batch_no, step, note or "")
            if step not in REPEATABLE and any(_key(d) == rec_key for d in done):
                raise StepError(f"'{step}' is already recorded for this item")
            needs = STEPS[step]
            if needs and not any(d["step"] == needs and d["cnf_code"] == cnf_code and d.get("batch_no") == batch_no
                                 and d.get("sku_code") == sku_code for d in done):
                raise StepError(f"'{step}' needs '{needs}' first")
            rec = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "cnf_code": cnf_code,
                   "sku_code": sku_code, "batch_no": batch_no, "step": step, "qty": qty, "by": by, "note": note}
            f.seek(0, os.SEEK_END)
            f.write(json.dumps(rec) + "\n")
            return rec
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
