"""FastAPI entrypoint. Vercel finds the FastAPI instance named `app` in app.py.

Run locally:   uvicorn app:app --reload        then open http://127.0.0.1:8000
On Vercel:     the files in public/ are served from the CDN; /api/* reaches this app.

Three tabs, three entry points:
  Claims desk           POST /api/claim/register, POST /api/claim/email
  Expiry & dispatch     POST /api/watch {"tab": "watch"}
  Allocation            POST /api/watch {"tab": "allocation"}
  Weekly digest         POST /api/watch {"tab": "weekly"}
New claims (ADR 0013): POST /api/intake/email, POST /api/intake/form, GET /api/intake,
                       POST /api/intake/status; stored in data/claims_store.jsonl
A citation's rows:     POST /api/source {"file", "rows", "offset"}
A person's approve/reject returns as a second request: POST /api/decision.
"""
import json
import os
import uuid
from datetime import date
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, BeforeValidator, Field

from agent import allocation, short_dated, stock, stock_log, store, tools
from agent.claim_nodes import _letter
from agent.audit import decision_lock, decisions_on, find_recommendation, log_kept, record_decision, subject_of
from agent.graph import run
from agent.watch import TAB_VIEWS

app = FastAPI(title="Project Sankalp pilot")

# Text from a person is trimmed BEFORE its length is checked, so "    " is empty, not a name (QA B5, B6).
Text = Annotated[str, BeforeValidator(lambda v: v.strip() if isinstance(v, str) else v)]
ROOT = Path(__file__).resolve().parent


SECURITY_HEADERS = {  # QA 21 Nov 2026 (D-01). vercel.json sets the same for files the CDN serves.
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
                               "connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'",
}


@app.middleware("http")
async def limit_body(request: Request, call_next):
    size = request.headers.get("content-length")
    if size and size.isdigit() and int(size) > MAX_BODY_BYTES:
        response = JSONResponse({"error": f"Request over {MAX_BODY_BYTES // 1024} KB"}, status_code=413)
    else:
        response = await call_next(request)
    response.headers.update(SECURITY_HEADERS)
    return response

OUTPUT_KEYS = ("route", "lines", "explanation", "reply", "status_facts", "digest", "watch",
               "citations", "errors", "usage", "audit_id", "read_by")
MAX_BODY_BYTES = 64 * 1024  # a claim request is a claim number or an email id; nothing near this


def _out(state: dict) -> dict:
    """What the page sees. Records stay server-side; dates become strings."""
    return json.loads(json.dumps({k: state.get(k) for k in OUTPUT_KEYS}, default=str))


def _guard(fn, *args):
    try:
        return _out(fn(*args))
    except ValueError as err:  # missing key or bad input: say so instead of a bare 500
        return JSONResponse({"error": str(err)}, status_code=503)
    except FileNotFoundError as err:
        return JSONResponse({"error": str(err)}, status_code=500)


@app.get("/api/health")
def health():
    """Quick check that the deployment is alive, the key is set and cleaned data is present."""
    return {"ok": True, "model_key_set": bool(os.getenv("OPENROUTER_API_KEY")),
            "clean_data": (ROOT / "data" / "clean" / "expiry_claims.csv").exists()}


# --- Claims desk ---------------------------------------------------------------------
@app.get("/api/claims")
def list_claims(status: str = "Pending", limit: int = Query(100, ge=1, le=1000)):
    df = tools.table("expiry_claims.csv")
    df = df[df["status"] == status].sort_values("claim_date").head(limit).copy()
    df["stockist_name"] = df["stockist_code"].map(_names("stockist_master.csv", "stockist_code", "stockist_name"))
    df["product"] = df["sku_code"].map(_names("sku_master.csv", "sku_code", "product_description"))
    for col in ("claim_date", "expiry_date_as_claimed"):
        df[col] = df[col].dt.strftime("%Y-%m-%d").fillna("")
    return json.loads(df[["claim_no", "claim_date", "stockist_code", "stockist_name", "sku_code", "product",
                          "batch_no", "qty_claimed", "claim_value_inr", "claim_type", "cnf_code",
                          "original_invoice_ref", "expiry_date_as_claimed"]].to_json(orient="records", date_format="iso"))


def _names(file: str, key: str, name: str) -> dict:
    t = tools.table(file)
    return dict(zip(t[key], t[name]))


@app.get("/api/emails")
def list_emails():
    """The mailbox, newest first, with the body so the page can show the email beside the result."""
    df = tools.table("claim_emails.csv").sort_values(["received_date", "email_id"], ascending=[False, True]).copy()
    df["received_date"] = df["received_date"].dt.strftime("%Y-%m-%d")
    return json.loads(df[["email_id", "received_date", "from_name", "stockist_code_by_mailbox_rule", "subject",
                          "body"]].to_json(orient="records"))


class RegisterClaim(BaseModel):
    claim_no: str


@app.post("/api/claim/register")
def claim_register(body: RegisterClaim):
    df = tools.table("expiry_claims.csv")
    hit = df[df["claim_no"] == body.claim_no.strip()]
    if hit.empty:
        raise HTTPException(404, f"Claim {body.claim_no} not in the register")
    return _guard(run, "register", hit.iloc[0].to_dict())


class EmailClaim(BaseModel):
    email_id: str


@app.post("/api/claim/email")
def claim_email(body: EmailClaim):
    df = tools.table("claim_emails.csv")
    hit = df[df["email_id"] == body.email_id.strip()]
    if hit.empty:
        raise HTTPException(404, f"Email {body.email_id} not found")
    return _guard(run, "email", hit.iloc[0].to_dict())


# --- New claims (ADR 0013) ------------------------------------------------------------
@app.get("/api/stockists")
def stockists():
    """For the New claim screens: the person picks the account; it is never read from text."""
    df = tools.table("stockist_master.csv")
    return json.loads(df[["stockist_code", "stockist_name", "city", "cnf_code"]].to_json(orient="records"))


class IntakeEmail(BaseModel):
    from_name: Text = Field("", max_length=120)
    stockist_code: Text | None = Field(None, max_length=20)  # from the mailbox the email came to; None = unknown
    subject: Text = Field("", max_length=300)
    body: Text = Field(min_length=1, max_length=20000)
    received_date: str | None = None


class FormLine(BaseModel):
    sku_text: str | None = Field(None, max_length=120)
    batch_no: str | None = Field(None, max_length=20)
    qty_claimed: float | None = None  # checked by rules.input_problems, so a bad value reaches a person with a reason
    claim_type: str | None = None
    invoice_ref: str | None = Field(None, max_length=40)
    expiry_text: str | None = Field(None, max_length=20)


class IntakeForm(BaseModel):
    stockist_code: str = Field(min_length=3, max_length=20)
    received_date: str | None = None
    entered_by: Text = Field(min_length=2, max_length=80)
    lines: list[FormLine] = Field(min_length=1, max_length=20)


def _stockist(code: str | None) -> dict | None:
    if not code:
        return None
    hit = tools.get_stockist(code)
    return hit["rows"][0] if hit["found"] else None


def _received(value: str | None) -> str:
    try:
        day = date.fromisoformat(value) if value else date.today()
    except ValueError:
        raise HTTPException(422, f"Date {value!r} is not YYYY-MM-DD")
    if day > date.today():
        raise HTTPException(422, "The received date cannot be in the future")
    return day.isoformat()


def _intake(entry: str, raw: dict, source: str, by: str) -> dict:
    """Check first (against the register and earlier new claims), then log every claim line
    with a claim number, then write the acknowledgement with those numbers."""
    state = run(entry, raw)
    lines = state.get("lines") or []
    numbers = []
    if state.get("email_kind") == "claim" and lines:
        for ln in lines:
            ln["audit_id"] = state.get("audit_id")
        numbers = store.register(lines, source=source, intake_ref=raw["email_id"], by=by,
                                 intake={k: raw.get(k) for k in ("from_name", "subject", "body") if raw.get(k)})
        for ln, no in zip(lines, numbers):
            ln["claim"]["claim_no"] = no
        state["reply"] = _letter(state)
    out = _out(state)
    out["registered"] = numbers
    return out


@app.post("/api/intake/email")
def intake_email(body: IntakeEmail):
    """A new email to the claims mailbox. The sender's account comes from the mailbox, not the text."""
    account = _stockist(body.stockist_code)
    if body.stockist_code and not account:
        raise HTTPException(422, f"Stockist {body.stockist_code} is not in the stockist master")
    raw = {"email_id": f"NEW-{uuid.uuid4().hex[:6].upper()}", "received_date": _received(body.received_date),
           "from_name": body.from_name or (account or {}).get("stockist_name", ""),
           "stockist_code_by_mailbox_rule": account["stockist_code"] if account else "",
           "subject": body.subject, "body": body.body}
    return _intake("email", raw, "email", "rules reader")


@app.post("/api/intake/form")
def intake_form(body: IntakeForm):
    """A new claim typed in by the claims desk or the C&F from the stockist's claim form (CO-POL-014 5.3)."""
    account = _stockist(body.stockist_code)
    if not account:
        raise HTTPException(422, f"Stockist {body.stockist_code} is not in the stockist master")
    raw = {"email_id": f"FORM-{uuid.uuid4().hex[:6].upper()}", "received_date": _received(body.received_date),
           "from_name": account["stockist_name"], "stockist_code_by_mailbox_rule": account["stockist_code"],
           "lines": [ln.model_dump() for ln in body.lines]}
    return _intake("form", raw, "form", body.entered_by.strip())


@app.get("/api/intake")
def intake_list():
    """New claims with their current status, history and due dates (10 working days to verify,
    30 days to the credit note, CO-POL-014 5.6)."""
    return json.loads(json.dumps(store.snapshot(), default=str))  # serialised copy; the cache is not changed


class StatusMove(BaseModel):
    claim_no: str
    status: Literal["Received", "Awaiting info", "Verified", "On hold", "Credit note raised", "Closed"]
    by: Text = Field(min_length=2, max_length=80)
    note: Text = Field("", max_length=1000)
    credit_note_no: Text | None = Field(None, max_length=40)


@app.post("/api/intake/status")
def intake_status(body: StatusMove):
    """Move a new claim along: verified at the CFA, credit note raised, closed. Approve and reject
    go through POST /api/decision, so they carry the recommendation and any override reason."""
    try:
        return store.move(body.claim_no, body.status, body.by.strip(), body.note, body.credit_note_no)
    except store.StoreError as err:
        raise HTTPException(409, str(err))


# --- Expiry & dispatch (ADR 0014) ------------------------------------------------------
@app.get("/api/stock/overview")
def stock_overview():
    """One card per CFA: stock, what needs action, and the batch-order check."""
    return stock.overview()


@app.get("/api/stock/plan")
def stock_plan(cfa: str):
    """One CFA's to-do list (block, consent, CDC return), pick order and batch-order check,
    with what people have already done about it."""
    try:
        out = stock.plan(cfa)
    except ValueError as err:
        raise HTTPException(404, str(err))
    out["actions"] = stock_log.actions(cfa)
    return json.loads(json.dumps(out, default=str))


class StockAction(BaseModel):
    cnf_code: str = Field(min_length=3, max_length=12)
    step: str
    by: Text = Field(min_length=2, max_length=80)
    sku_code: Text | None = None
    batch_no: Text | None = None
    qty: int | None = Field(None, ge=1)
    note: Text = Field("", max_length=500)


CONSENT_STEPS = {"Stockist agreed", "No agreement on record"}


def _check_target(body: "StockAction") -> None:
    """A step must be about something in the plan (QA B3): a CFA in the stock snapshot (or
    NATIONAL for scheme steps), a product in the SKU master, and a batch that CFA holds."""
    if body.step in CONSENT_STEPS:  # a past dispatch: the batch may be gone, so check the flagged line instead
        hits = short_dated.lines()
        hits = hits[(hits["cnf_code"] == body.cnf_code) & (hits["batch_no"] == body.batch_no) & (hits["sku_code"] == body.sku_code)
                    & (hits["invoice_no"] == (body.note or "").removeprefix("Invoice "))]
        if hits.empty:
            raise HTTPException(422, "Not a flagged short-dated dispatch: give cnf_code, sku_code, batch_no and note 'Invoice <no>'")
        return
    national = body.cnf_code == "NATIONAL"
    if national != (body.step in stock_log.SCHEME_STEPS):
        raise HTTPException(422, "Scheme steps are national; every other step belongs to a CFA")
    if national:
        return
    b = stock.batches()
    if body.cnf_code not in set(b["cnf_code"]):
        raise HTTPException(422, f"{body.cnf_code} is not a CFA in the stock snapshot")
    if body.sku_code and body.sku_code not in set(tools.table("sku_master.csv")["sku_code"]):
        raise HTTPException(422, f"{body.sku_code} is not in the SKU master")
    if body.batch_no:
        held = b[(b["cnf_code"] == body.cnf_code) & (b["batch_no"] == body.batch_no)]
        if held.empty or (body.sku_code and body.sku_code not in set(held["sku_code"])):
            raise HTTPException(422, f"{body.cnf_code} holds no batch {body.batch_no}"
                                     f"{' of ' + body.sku_code if body.sku_code else ''}")


@app.post("/api/stock/action")
def stock_action(body: StockAction):
    """Record what a person did: blocked a batch, offered it with consent, requested or approved
    a CDC return, confirmed the pick order, raised the batch-order alert with the CFA."""
    _check_target(body)
    try:
        return stock_log.record(body.cnf_code, body.step, body.by.strip(), body.sku_code, body.batch_no,
                                body.qty, body.note)
    except stock_log.StepError as err:
        raise HTTPException(409, str(err))


# --- Dispatches under 60% shelf life (plan step 4) ---------------------------------------
@app.get("/api/stock/short-dated")
def short_dated_summary():
    """Every dispatch billed under 60% shelf life in the last four quarters: totals, where it piles up
    (C&F, product, stockist, batch) and the likely reasons (CO-POL-014 7.1)."""
    out = short_dated.summary()
    acts = [a for a in stock_log.actions() if a["step"] in CONSENT_STEPS]
    out["consent"] = {"agreed": sum(a["step"] == "Stockist agreed" for a in acts),
                      "no_agreement": sum(a["step"] == "No agreement on record" for a in acts)}
    return _clean(out)


@app.get("/api/stock/short-dated/lines")
def short_dated_lines(cfa: str, reason: str | None = None, offset: int = Query(0, ge=0)):
    """One C&F's flagged dispatch lines, newest first, 50 a page, with consent steps recorded so far."""
    try:
        out = short_dated.for_cfa(cfa, reason, offset)
    except ValueError as err:
        raise HTTPException(404 if "No short-dated" in str(err) else 422, str(err))
    out["actions"] = [a for a in stock_log.actions(cfa) if a["step"] in CONSENT_STEPS]
    return _clean(out)


# --- Allocation on demand from invoices (plan step 2) ------------------------------------
def _clean(obj):
    return json.loads(json.dumps(obj, default=lambda v: float(v) if hasattr(v, "item") else str(v)))


Basis = Literal["current", "fy25"]


@app.get("/api/allocation/overview")
def allocation_overview(basis: Basis = "current"):
    """National figures and one card per C&F: months of stock on allocated volume (both share
    bases), statuses, this month's top-up, excess and returns, orders not filled."""
    return _clean(allocation.overview(basis))


@app.get("/api/allocation/plan")
def allocation_plan(cfa: str, basis: Basis = "current"):
    """One C&F's products by status (out of stock, below target, excess, on target) with what to
    do, and the orders it could not fill in the last six months."""
    try:
        out = allocation.plan(cfa, basis)
    except ValueError as err:
        raise HTTPException(404, str(err))
    out["actions"] = stock_log.actions(cfa)
    return _clean(out)


@app.get("/api/allocation/topups")
def allocation_topups(basis: Basis = "current"):
    """This month's replenishment from the CDC, per C&F (CF Sch 2 2.2; assumes the CDC can supply)."""
    return _clean({**allocation.topups(basis), "actions": stock_log.actions()})


@app.get("/api/allocation/returns")
def allocation_returns(basis: Basis = "current"):
    """Returns to the CDC under the client's rules, with the batches that qualify."""
    return _clean({**allocation.returns(basis), "actions": stock_log.actions()})


@app.get("/api/allocation/shares")
def allocation_shares():
    """FY25 against current shares per C&F: the share change recommended to the client."""
    return _clean({**allocation.shares(), "actions": stock_log.actions("NATIONAL")})


@app.get("/api/allocation/restatement")
def allocation_restatement():
    """Old figure, new figure and reason, side by side (client, 22 Nov 2026)."""
    return _clean({"rows": allocation.restatement()})


@app.get("/api/allocation/schemes")
def allocation_schemes():
    """For the NSM and CFO: claim rate on scheme products and free goods against the 3% cap."""
    return _clean({**allocation.schemes(), "actions": [a for a in stock_log.actions("NATIONAL")]})


# --- Weekly digest (ADR 0016) ----------------------------------------------------------
@app.get("/api/digest")
def weekly_digest():
    """One section per owner: key figures, top things to do (with the screen to do them on),
    what has been done, and the same digest as plain text for an email."""
    from agent import digest
    return _clean(digest.build())


# --- Watch tabs ------------------------------------------------------------------------
class Watch(BaseModel):
    tab: Literal["watch", "allocation", "weekly"] = "weekly"


@app.post("/api/watch")
def watch(body: Watch):
    return _guard(run, "watch", {"views": TAB_VIEWS[body.tab]})


# --- Source-row viewer ---------------------------------------------------------------
class Source(BaseModel):
    file: str
    rows: list[int]
    offset: int = Field(0, ge=0)


@app.post("/api/source")
def source(body: Source):
    """The rows a citation points at, so a reviewer can see the record behind a number."""
    try:
        return json.loads(json.dumps(tools.source_rows(body.file, body.rows, body.offset), default=str))
    except ValueError as err:
        raise HTTPException(400, str(err))


# --- Human decision --------------------------------------------------------------------
Route = Literal["clean", "to_person", "reject", "needs_person", "already_decided", "reply"]
OVERRIDES = {("reject", "approve"), ("needs_person", "approve"), ("clean", "reject")}
MIN_REASON = 10


class Decision(BaseModel):
    audit_id: str = Field(min_length=6, max_length=64)
    decided_by: Text = Field(min_length=2, max_length=80)
    decision: Literal["approve", "reject", "hold"]
    note: Text = Field("", max_length=1000)
    recommended: Route | None = None  # used only when the server did not keep the recommendation
    claim_no: str | None = None  # a new claim in the store: its status follows the decision


@app.post("/api/decision")
def decision(body: Decision):
    with decision_lock():
        return _decide(body)


def _decide(body: Decision):
    """Every credit note is signed by a person. Nothing is auto-approved in v1.
    - An already settled claim cannot be approved: that would be a second credit.
    - Going against the recommendation (approving a reject, rejecting a clean claim) needs a
      written reason, logged as an override.
    The recommendation is taken from the server's log when it has one, not from the page.
    One decision per claim (QA B1, B2):
    - Where the server keeps its log, the audit id must be one it issued (404 otherwise).
    - A claim or email already decided, under any audit id, cannot get the same decision again
      (409). Changing the decision needs a written reason and is logged with what it changes."""
    if len(body.decided_by) < 2:
        raise HTTPException(422, "Enter the name of the person deciding")
    logged = find_recommendation(body.audit_id)
    if logged is None and log_kept() and not body.claim_no:
        raise HTTPException(404, f"No recommendation {body.audit_id} on this server; check the claim again")
    recommended = logged.get("route") if logged else body.recommended
    subject = body.claim_no or (subject_of(logged) if logged else None)
    changes = None
    if subject and not body.claim_no:
        earlier = decisions_on(subject)
        if earlier:
            last = earlier[-1]
            when = str(last.get("at", ""))[:10]
            if last["decision"] == body.decision:
                raise HTTPException(409, f"Already {last['decision']}d by {last['decided_by']} on {when}; "
                                         "a second decision would count it twice")
            if len(body.note) < MIN_REASON:
                raise HTTPException(422, f"Already {last['decision']}d by {last['decided_by']} on {when}. To change "
                                         f"it, give the reason (at least {MIN_REASON} characters)")
            changes = {"decision": last["decision"], "decided_by": last["decided_by"], "at": last.get("at")}
    if recommended == "already_decided" and body.decision == "approve":
        raise HTTPException(409, "This claim is already settled; approving it would credit it twice")
    override = (recommended, body.decision) in OVERRIDES
    if override and len(body.note) < MIN_REASON:
        raise HTTPException(422, f"Going against the recommendation ({recommended}) needs a reason of at least "
                                 f"{MIN_REASON} characters")
    if body.claim_no:
        stored = store.get(body.claim_no)
        if stored is None:
            raise HTTPException(404, f"{body.claim_no} is not a new claim in the store")
        recommended = stored.get("route") or recommended
        override = (recommended, body.decision) in OVERRIDES
        if override and len(body.note) < MIN_REASON:
            raise HTTPException(422, f"Going against the recommendation ({recommended}) needs a reason of at least "
                                     f"{MIN_REASON} characters")
        try:
            store.decide(body.claim_no, body.decision, body.decided_by, body.note, override)
        except store.StoreError as err:
            raise HTTPException(409, str(err))
    return record_decision(body.audit_id, body.decided_by, body.decision, body.note, recommended, override,
                           subject, changes)


@app.get("/")
def index():
    return FileResponse(ROOT / "public" / "index.html")


# On Vercel the public/ folder is served by the platform, and Vercel's docs say not to
# mount it. On your laptop nothing serves it, so mount it only when not on Vercel.
if not os.getenv("VERCEL"):
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=ROOT / "public"), name="public")
