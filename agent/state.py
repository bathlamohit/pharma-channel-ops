"""Graph state. Every value that holds a number also holds its citation."""
from typing import Annotated, Literal, TypedDict

from pydantic import BaseModel, Field

Entry = Literal["email", "register", "form", "watch"]  # form: a new claim typed in by the desk
EmailKind = Literal["claim", "status_query", "not_a_claim"]
CheckOutcome = Literal["pass", "fail", "flag", "skip"]
Route = Literal["reject", "to_person", "clean", "needs_person", "reply", "already_decided"]


class Citation(TypedDict):
    file: str  # raw file name, e.g. "primary_sales.csv"
    rows: list[int]  # original line numbers in the raw file (header is line 1)
    snapshot: str  # extract date, ISO


class CheckResult(TypedDict):
    check: str
    outcome: CheckOutcome
    clause: str
    on_fail: Literal["reject", "to_person"]
    detail: str
    citations: list[Citation]


class WatchResult(TypedDict):
    view: str
    owner: str  # who acts on it in the weekly digest
    rows: list[dict]
    summary: str
    citations: list[Citation]


# --- Structured output for extract_claim (the model fills this form, nothing else) ---
class ClaimFields(BaseModel):
    """One claim line, copied as written. The sender's identity is NOT taken from here:
    it comes from the mailbox rule, so an email cannot claim to be another stockist."""
    sku_text: str | None = Field(None, description="Product as written")
    batch_no: str | None = Field(None, description="Batch as written, character for character")
    expiry_text: str | None = Field(None, description="Expiry as written, e.g. 'Oct-26', '09/2026'")
    qty_claimed: int | None = Field(None, description="Strips/packs claimed. If given as boxes of N strips, boxes x N")
    claim_type: Literal["Near expiry", "Expired", "Short supply", "Breakage in transit"] | None = Field(
        None, description="Only if the email says breakage or short supply; otherwise leave empty")
    invoice_ref: str | None = Field(None, description="Invoice number as written, if any")


class ExtractedEmail(BaseModel):
    kind: EmailKind = Field(description="claim: asks for credit on stock; status_query: asks about an "
                                        "earlier claim; not_a_claim: anything else")
    claims: list[ClaimFields] = Field(default_factory=list, description="One entry per claim line, "
                                      "for status queries the batch they ask about, if any")
    claim_refs: list[str] = Field(default_factory=list, description="Claim numbers mentioned, e.g. CLM-2608-02444")


def merge(left: dict | None, right: dict | None) -> dict:
    """Reducer for keys written by parallel nodes."""
    return {**(left or {}), **(right or {})}


def concat(left: list | None, right: list | None) -> list:
    return [*(left or []), *(right or [])]


class ClaimState(TypedDict, total=False):
    """One claim line through the claim subgraph."""
    claim: dict  # normalised claim fields
    siblings: list[dict]  # earlier lines of the same email: they count as prior claims
    records: dict  # stockist, batch, sku, supplies, prior_claims, invoice, each with citations
    checks: Annotated[dict[str, CheckResult], merge]
    route: Route
    recommendation: dict  # rules.recommend: action, qty, credit_inr, reason_codes
    errors: Annotated[list[str], concat]


class LineResult(TypedDict):
    claim: dict
    checks: dict[str, CheckResult]
    route: Route
    errors: list[str]
    recommendation: dict


class SankalpState(TypedDict, total=False):
    # Input
    entry: Entry
    raw_input: dict  # email row, register row, or {"views": [...]} for watch
    # Claim path
    email_kind: EmailKind
    read_by: str  # "rules", "model" (fallback only) or "nobody" (a person reads it)
    claims: list[dict]  # normalised claim lines
    claim_refs: list[str]
    status_batches: list[str]  # batches a status query asks about
    lines: list[LineResult]  # one per claim line
    route: Route  # overall: reject / clean only when every line agrees, else to_person
    status_facts: list[str]  # register facts a status reply may state
    reply: str
    # Watch path
    views: list[str]
    watch: Annotated[dict[str, WatchResult], merge]
    digest: dict
    # Output
    explanation: str
    model_text: list[str]  # output keys a model wrote; only these pass through the number guard
    citations: Annotated[list[Citation], concat]
    errors: Annotated[list[str], concat]
    usage: Annotated[list[dict], concat]  # model calls, tokens, seconds
    audit_id: str
    decision: dict  # filled by POST /api/decision, never by the graph
