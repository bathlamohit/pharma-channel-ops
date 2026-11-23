"""Read a claims-mailbox email with rules, not a model.

The form is the same one the model fills (ExtractedEmail), so everything downstream is
unchanged. The reader returns None only when it finds nothing it recognises: no claim
number, no batch, no claim or status words, and no topic from policy.FORWARD_RULES.
Only then is the model asked (if a key is set); otherwise a person reads the email.

What it recognises, from the mailbox (tests/check_set.json holds the agreed answers):
- batch numbers: a letter, two digits, five digits; a letter O typed for zero is kept as
  written (get_batch corrects it only when exactly one batch matches)
- quantities: "241 strips", "qty 226", "147 strip", "43 boxes (10 strips each)" = 430,
  or the Qty column of a | table
- expiry: "exp Oct-26", "expiry Mar 2027", "expiring Oct-26", "exp 31-10-2026", "09/2026"
- invoice numbers in any separator style; claim numbers CLM-yymm-nnnnn
- breakage and short-supply wording (near expiry vs expired is set from the batch master)
"""
import re

from agent import policy
from agent.state import ClaimFields, ExtractedEmail

BATCH = re.compile(r"\b([A-Z]\d{2}[0-9O]{5})\b")
INVOICE = re.compile(r"\bINV[-/ ]?[A-Z]\d{2}[-/ ]\d{4}[-/ ]\d{6}\b", re.I)
CLAIM_REF = re.compile(r"\bCLM-\d{4}-\d{5}\b", re.I)
BOXES = re.compile(r"(\d[\d,]*)\s*(?:boxes|box|cartons?)\s*\(?\s*(?:of\s*)?(\d+)\s*(?:strips?|packs?)\s*(?:each)?", re.I)
QTY_WORD = re.compile(r"\b(?:qty|quantity)\s*[:\-=]?\s*(\d[\d,]*)", re.I)
QTY_UNIT = re.compile(r"\b(\d[\d,]*)\s*(?:strips?|packs?|pcs|bottles?|units|tabs?|dabbe)\b", re.I)
EXPIRY = re.compile(r"\bexp(?:iry|iring|\.)?\s*(?:date)?\s*[:\-]?\s*"
                    r"(\d{1,2}[-/.]\d{1,2}[-/.]\d{4}|\d{1,2}[-/]\d{4}|[A-Za-z]{3,9}[-' ]?\d{2,4})", re.I)
EXPIRY_CELL = re.compile(r"^(\d{1,2}[-/.]\d{1,2}[-/.]\d{4}|\d{1,2}[-/]\d{4}|[A-Za-z]{3,9}[-' ]?\d{2,4})$")

CLAIM_WORDS = re.compile(r"expir|near expiry|claim|return|breakage|broken|damaged|short supply|"
                         r"short received|credit|wapas|take back", re.I)
STATUS_WORDS = re.compile(r"\bstatus\b|what happened|any update|not received|credit note\s*\?", re.I)
BREAKAGE = re.compile(r"breakage|broken|damaged|leak", re.I)
SHORT = re.compile(r"short supply|short received|received less|fewer|missing packs", re.I)


def _num(s: str) -> int:
    return int(s.replace(",", ""))


def _quantity(text: str) -> int | None:
    m = BOXES.search(text)
    if m:
        return _num(m[1]) * int(m[2])
    for pattern in (QTY_WORD, QTY_UNIT):
        m = pattern.search(text)
        if m:
            return _num(m[1])
    return None


def _claim_type(text: str) -> str | None:
    if BREAKAGE.search(text):
        return "Breakage in transit"
    if SHORT.search(text):
        return "Short supply"
    return None


def _sku_text(line: str, batch: str | None) -> str | None:
    head = line.split(batch)[0] if batch and batch in line else line
    head = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", head)  # list markers
    head = re.sub(r"(?i)\b(batch|b\.?no\.?)\b.*$", "", head).strip(" ,:-|")
    head = re.sub(r"(?i)^.*?\b(?:return|claim|paas|accept)\b[:\s]*", "", head).strip(" ,:-|")
    # a greeting at the start of the line is not a product (QA D-08)
    head = re.sub(r"(?i)^(?:dear\s+(?:sir|madam|team|pfizer)(?:/madam)?|hi(?:\s+team)?|hello|namaste(?:\s+ji)?|sir)\b[,:\s]*",
                  "", head).strip(" ,:-|")
    return head or None


def _table(lines: list[str]) -> list[ClaimFields] | None:
    """A | table with a header row naming Batch and Qty."""
    header = next((i for i, ln in enumerate(lines) if "|" in ln and re.search(r"batch", ln, re.I)
                   and re.search(r"qty|quantity", ln, re.I)), None)
    if header is None:
        return None
    cols = [c.strip().lower() for c in lines[header].split("|")]

    def col(*names):
        return next((i for i, c in enumerate(cols) if any(n in c for n in names)), None)

    ib, iq, ie, ii, ip = col("batch"), col("qty", "quantity"), col("exp"), col("inv"), col("product", "item", "sku")
    out = []
    for ln in lines[header + 1:]:
        if "|" not in ln:
            continue
        cells = [c.strip() for c in ln.split("|")]
        get = lambda i: cells[i] if i is not None and i < len(cells) and cells[i] else None  # noqa: E731
        qty = get(iq)
        out.append(ClaimFields(sku_text=get(ip), batch_no=get(ib), expiry_text=get(ie),
                               qty_claimed=_num(qty) if qty and re.fullmatch(r"\d[\d,]*", qty) else None,
                               invoice_ref=get(ii), claim_type=_claim_type(ln)))
    return out


def _lines(text: str) -> list[ClaimFields]:
    lines = text.splitlines()
    table = _table(lines)
    if table is not None:
        return table
    out = []
    for ln in lines:
        batches = BATCH.findall(ln)
        if not batches:
            continue
        exp = EXPIRY.search(ln)
        inv = INVOICE.search(ln)
        out.append(ClaimFields(sku_text=_sku_text(ln, batches[0]), batch_no=batches[0],
                               expiry_text=exp[1] if exp else None, qty_claimed=_quantity(ln),
                               invoice_ref=inv[0] if inv else None, claim_type=_claim_type(ln)))
    if out:
        # A single line whose invoice or expiry is written on another line (EML-008)
        if len(out) == 1:
            invoices, exp = INVOICE.findall(text), EXPIRY.search(text)
            fill = {}
            if not out[0].invoice_ref and len(set(invoices)) == 1:
                fill["invoice_ref"] = invoices[0]
            if not out[0].expiry_text and exp:
                fill["expiry_text"] = exp[1]
            if out[0].qty_claimed is None and _quantity(text) is not None:
                fill["qty_claimed"] = _quantity(text)
            out[0] = out[0].model_copy(update=fill)
        return out
    qty = _quantity(text)  # a claim without a batch (EML-006): kept, so a person asks for the batch
    if qty is not None:
        exp = EXPIRY.search(text)
        return [ClaimFields(qty_claimed=qty, expiry_text=exp[1] if exp else None, claim_type=_claim_type(text))]
    return []


def forward_to(text: str) -> str | None:
    for pattern, team in policy.FORWARD_RULES:
        if re.search(pattern, text, re.I):
            return team
    return None


def read_email(email: dict) -> ExtractedEmail | None:
    text = f"{email.get('subject') or ''}\n{email.get('body') or ''}"
    refs = sorted({r.upper() for r in CLAIM_REF.findall(text)})
    claims = _lines(email.get("body") or "")
    has_qty = any(c.qty_claimed for c in claims)
    if refs and not has_qty:
        return ExtractedEmail(kind="status_query", claims=claims, claim_refs=refs)
    if STATUS_WORDS.search(text) and not has_qty:
        return ExtractedEmail(kind="status_query", claims=claims, claim_refs=refs)
    if claims or CLAIM_WORDS.search(text):
        return ExtractedEmail(kind="claim", claims=claims, claim_refs=refs)
    if forward_to(text):
        return ExtractedEmail(kind="not_a_claim")
    return None
