"""The eight claim checks of CO-POL-014 section 5. Pure functions, no model, one test each.

Each takes the normalised claim and the records resolve_records found, and returns a
CheckResult with outcome, clause and the rows it used. Outcomes:
  pass  - rule met
  fail  - rule broken; on_fail says reject or to_person
  flag  - cannot confirm; goes to a person with the reason
  skip  - not applicable to this claim type
Thresholds come from agent/policy.py only.
"""
import math
from datetime import date, datetime

from agent import policy
from agent.state import CheckResult, Citation

REJECTED = "Rejected"


def _d(v) -> date | None:
    if v is None or v == "" or v != v:  # v != v catches NaN / NaT
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def _f(v) -> float:
    try:
        return float(str(v).replace(",", ""))
    except ValueError:
        return 0.0


def _cites(*recs: dict | None) -> list[Citation]:
    return [r["citation"] for r in recs if r and r.get("citation")]


def _result(check, outcome, clause, on_fail, detail, *recs) -> CheckResult:
    return {"check": check, "outcome": outcome, "clause": clause, "on_fail": on_fail,
            "detail": detail, "citations": _cites(*recs)}


def _other_claims(claim: dict, records: dict) -> list[dict]:
    rows = (records.get("prior_claims") or {}).get("rows", [])
    return [r for r in rows if r.get("claim_no") != claim.get("claim_no") and r.get("status") != REJECTED]


def _is_earlier(other: dict, claim: dict) -> bool:
    """Ordered by claim date, then claim number. A claim with no number (a new email) is last."""
    mine = (_d(claim.get("claim_date")) or date.max, claim.get("claim_no") or "~")
    theirs = (_d(other.get("claim_date")) or date.max, other.get("claim_no") or "~")
    return theirs < mine


# 1 ------------------------------------------------------------------------------------
def chk_duplicate(claim: dict, records: dict) -> CheckResult:
    """Same stockist, batch and quantity ALREADY claimed (C&F procedure 2.6.3). Fail: reject.
    Only earlier, non-rejected claims count, so the first of a pair passes."""
    same = [r for r in _other_claims(claim, records)
            if _is_earlier(r, claim) and _f(r["qty_claimed"]) == _f(claim["qty_claimed"])]
    if same:
        return _result("duplicate", "fail", policy.DUPLICATE_CLAUSE, "reject",
                       f"Already claimed as {', '.join(r['claim_no'] for r in same)}", records.get("prior_claims"))
    return _result("duplicate", "pass", policy.DUPLICATE_CLAUSE, "reject", "No earlier claim with this quantity",
                   records.get("prior_claims"))


# 2 ------------------------------------------------------------------------------------
def chk_window(claim: dict, records: dict) -> CheckResult:
    """Any claim raised over 90 days after the batch expires: reject.
    Near expiry raised over 90 days before expiry: to a person (decision D2).
    Breakage or short supply over 7 days after the referenced invoice: reject (CO-POL-014 5.2).
    Expiry comes from the batch master, never from the claim."""
    kind, claimed_on = claim.get("claim_type"), _d(claim.get("claim_date"))
    batch = records.get("batch") or {}
    expiry = _d(batch["rows"][0]["expiry_date"]) if batch.get("found") else None
    if claimed_on and expiry:
        days_after = (claimed_on - expiry).days
        if days_after > policy.EXPIRED_AFTER_DAYS.value:
            return _result("window", "fail", policy.WINDOW_CLAUSE, "reject",
                           f"Raised {days_after} days after expiry; limit is 90", batch)

    if kind in ("Near expiry", "Expired"):
        if not (claimed_on and expiry):
            return _result("window", "flag", policy.WINDOW_CLAUSE, "to_person", "Claim or expiry date missing", batch)
        days_to_expiry = (expiry - claimed_on).days
        if kind == "Near expiry" and days_to_expiry > policy.NEAR_EXPIRY_BEFORE_DAYS.value:
            return _result("window", "fail", policy.WINDOW_CLAUSE, "to_person",
                           f"Raised {days_to_expiry} days before expiry; window opens at 90", batch)
        return _result("window", "pass", policy.WINDOW_CLAUSE, "reject", "Inside the expiry window", batch)

    invoice = records.get("invoice") or {}
    inv_date = _d(invoice["rows"][0]["invoice_date"]) if invoice.get("found") else None
    if not (claimed_on and inv_date):
        return _result("window", "flag", policy.WINDOW_CLAUSE, "to_person", "Invoice date not found", invoice)
    late = (claimed_on - inv_date).days
    if late > policy.BREAKAGE_SHORT_DAYS.value:
        return _result("window", "fail", policy.WINDOW_CLAUSE, "reject", f"Raised {late} days after invoice; limit is 7", invoice)
    return _result("window", "pass", policy.WINDOW_CLAUSE, "reject", "Within 7 days of invoice", invoice)


# 3 ------------------------------------------------------------------------------------
def chk_supplied(claim: dict, records: dict) -> CheckResult:
    """Batch billed to this stockist before the claim date (CO-POL-014 5.5). Fail: reject."""
    supplies = records.get("supplies") or {}
    if supplies.get("found"):
        return _result("supplied", "pass", policy.SUPPLIED_CLAUSE, "reject", "Batch was billed to this stockist", supplies)
    return _result("supplied", "fail", policy.SUPPLIED_CLAUSE, "reject",
                   "This batch was never billed to this stockist before the claim", supplies)


# 4 ------------------------------------------------------------------------------------
def quantity_figures(claim: dict, records: dict) -> tuple[float, float, float]:
    """(supplied incl. free, claimed earlier on this batch, still claimable) for CO-POL-014 5.5."""
    supplies = records.get("supplies") or {}
    supplied = sum(_f(r["invoiced_qty"]) + _f(r["free_qty"]) for r in supplies.get("rows", []))
    earlier = sum(_f(r["qty_claimed"]) for r in _other_claims(claim, records))
    return supplied, earlier, max(supplied - earlier, 0.0)


def chk_quantity(claim: dict, records: dict) -> CheckResult:
    """All claims on the batch by this stockist <= packs supplied, free included (CO-POL-014 5.5).
    Fail: to a person, showing the excess and what is still claimable."""
    supplies = records.get("supplies") or {}
    supplied, earlier, _ = quantity_figures(claim, records)
    claimed = _f(claim["qty_claimed"]) + earlier
    if claimed > supplied:
        return _result("quantity", "fail", policy.QUANTITY_CLAUSE, "to_person",
                       f"{claimed:.0f} claimed against {supplied:.0f} supplied; excess {claimed - supplied:.0f}",
                       supplies, records.get("prior_claims"))
    return _result("quantity", "pass", policy.QUANTITY_CLAUSE, "to_person",
                   f"{claimed:.0f} claimed of {supplied:.0f} supplied", supplies, records.get("prior_claims"))


# 5 ------------------------------------------------------------------------------------
def chk_invoice_ref(claim: dict, records: dict) -> CheckResult:
    """Reference present, and the invoice shows this batch to this stockist (CO-POL-014 5.3, 5.4).
    Fail: to a person."""
    if not claim.get("invoice_ref"):
        return _result("invoice_ref", "fail", policy.INVOICE_REF_CLAUSE, "to_person", "No invoice reference given")
    invoice = records.get("invoice") or {}
    match = [r for r in invoice.get("rows", [])
             if r["stockist_code"] == claim["stockist_code"] and r["batch_no"] == claim["batch_no"]]
    if not match:
        return _result("invoice_ref", "fail", policy.INVOICE_REF_CLAUSE, "to_person",
                       "Invoice does not show this batch to this stockist", invoice)
    return _result("invoice_ref", "pass", policy.INVOICE_REF_CLAUSE, "to_person", "Invoice matches", invoice)


# 6 ------------------------------------------------------------------------------------
def chk_batch(claim: dict, records: dict) -> CheckResult:
    """Batch exists; product and expiry match. Made before Oct 2023: unverifiable. Fail: to a person."""
    batch = records.get("batch") or {}
    if not batch.get("found"):
        return _result("batch", "fail", policy.BATCH_CLAUSE, "to_person", "Batch not in the batch master")
    row = batch["rows"][0]
    problems = []
    if claim.get("sku_code") and row["sku_code"] != claim["sku_code"]:
        problems.append(f"batch is {row['sku_code']}, claim says {claim['sku_code']}")
    claimed_exp, batch_exp = _d(claim.get("expiry_date_as_claimed")), _d(row["expiry_date"])
    if claimed_exp and batch_exp and (claimed_exp.year, claimed_exp.month) != (batch_exp.year, batch_exp.month):
        problems.append(f"claim says expiry {claimed_exp:%b %Y}, batch master says {batch_exp:%b %Y}")
    mfg = _d(row["mfg_date"])
    if mfg and mfg < policy.BATCH_VERIFIABLE_FROM:
        problems.append("made before Oct 2023: cannot be verified")
    if batch.get("corrected"):
        problems.append(f"batch number corrected {batch['corrected']['from']} -> {batch['corrected']['to']}")
    if problems:
        return _result("batch", "flag", policy.BATCH_CLAUSE, "to_person", "; ".join(problems), batch)
    return _result("batch", "pass", policy.BATCH_CLAUSE, "to_person", "Batch, product and expiry match", batch)


# 7 ------------------------------------------------------------------------------------
def chk_value(claim: dict, records: dict) -> CheckResult:
    """Claim value = quantity x PTS (CO-POL-014 5.7). Fail: to a person, showing the right value."""
    sku = (records.get("batch") or {}).get("sku") or {}
    if not sku.get("found"):
        return _result("value", "flag", policy.VALUE_CLAUSE, "to_person", "PTS not found for this product")
    expected = round(_f(claim["qty_claimed"]) * _f(sku["rows"][0]["pts_inr"]), 2)
    stated = claim.get("claim_value_inr")
    if stated in (None, ""):
        return _result("value", "pass", policy.VALUE_CLAUSE, "to_person", f"Value set at {expected:.2f}", sku)
    if abs(_f(stated) - expected) > policy.VALUE_TOLERANCE_INR.value:
        return _result("value", "fail", policy.VALUE_CLAUSE, "to_person",
                       f"Claimed {_f(stated):.2f}; quantity x PTS is {expected:.2f}", sku)
    return _result("value", "pass", policy.VALUE_CLAUSE, "to_person", "Value matches quantity x PTS", sku)


# 8 ------------------------------------------------------------------------------------
def chk_cfa(claim: dict, records: dict) -> CheckResult:
    """Returns are received only at the CFA that billed the stock (CO-POL-014 5.1).
    Emails carry no CFA: the billing CFA is taken from the supplies. Fail: to a person."""
    supplies = records.get("supplies") or {}
    billed = sorted({r["cnf_code"] for r in supplies.get("rows", []) if r.get("cnf_code")})
    lodged = claim.get("cnf_code")
    if not billed:
        return _result("cfa", "skip", policy.HOME_CFA_CLAUSE, "to_person", "No supply found to compare", supplies)
    if not lodged:
        return _result("cfa", "pass", policy.HOME_CFA_CLAUSE, "to_person",
                       f"Send the goods to {', '.join(billed)}, the CFA that billed them", supplies)
    if lodged not in billed:
        return _result("cfa", "fail", policy.HOME_CFA_CLAUSE, "to_person",
                       f"Lodged at {lodged}; the stock was billed by {', '.join(billed)}", supplies)
    return _result("cfa", "pass", policy.HOME_CFA_CLAUSE, "to_person", f"Lodged at {lodged}, the billing CFA", supplies)


CHECKS = {
    "chk_duplicate": chk_duplicate,
    "chk_window": chk_window,
    "chk_supplied": chk_supplied,
    "chk_quantity": chk_quantity,
    "chk_invoice_ref": chk_invoice_ref,
    "chk_batch": chk_batch,
    "chk_value": chk_value,
    "chk_cfa": chk_cfa,
}


# --- Input checks: a claim no stockist could make never reaches the rules --------------
def input_problems(claim: dict, today: date | None = None) -> list[str]:
    """Quantity a whole number of packs, at least 1; claim type one of CO-POL-014 5.2;
    claim date present and not in the future. Each problem sends the line to a person."""
    problems = []
    qty = claim.get("qty_claimed")
    if qty in (None, ""):
        problems.append("No quantity on the claim (CO-POL-014 5.3)")
    else:
        q = _f(qty) if not isinstance(qty, (int, float)) else float(qty)
        if math.isnan(q) or q < 1 or q != int(q):
            problems.append(f"Quantity {qty} is not a whole number of packs of at least 1 (CO-POL-014 5.3)")
    kind = claim.get("claim_type")
    if kind and kind not in policy.CLAIM_TYPES:
        problems.append(f"Claim type {kind!r} is not one of {', '.join(policy.CLAIM_TYPES)} (CO-POL-014 5.2)")
    claimed_on = _d(claim.get("claim_date"))
    if claimed_on is None:
        problems.append("No claim date")
    elif claimed_on > (today or date.today()):
        problems.append(f"Claim date {claimed_on.isoformat()} is in the future")
    return problems


SETTLED = ("Credited", "Rejected")


def recommend(claim: dict, checks: dict[str, CheckResult], records: dict, route: str) -> dict:
    """What the desk should do with the line, in money: code, not a model.
    approve        every check passes; credit = quantity x PTS (CO-POL-014 5.7)
    approve_part   only the quantity limit fails; credit the packs still claimable (5.5),
                   for a person to confirm: the policy sets the limit, not whether to part-approve
    reject         a hard rule fails (window, duplicate, never supplied)
    review         anything else a person must judge, with the reason codes
    """
    sku = (records.get("batch") or {}).get("sku") or {}
    pts = _f(sku["rows"][0]["pts_inr"]) if sku.get("found") else None
    qty = _f(claim.get("qty_claimed"))
    bad = [k for k, r in checks.items() if r["outcome"] in ("fail", "flag")]
    codes = [policy.REASON_CODE[k] for k in bad if k in policy.REASON_CODE]

    def money(n):
        return round(n * pts, 2) if pts is not None else None

    if route == "reject":
        return {"action": "reject", "qty": 0, "credit_inr": 0.0, "reason_codes": codes}
    if route == "clean":
        return {"action": "approve", "qty": int(qty), "credit_inr": money(qty), "reason_codes": []}
    if bad == ["chk_quantity"]:
        _, _, left = quantity_figures(claim, records)
        if left >= 1:
            return {"action": "approve_part", "qty": int(left), "credit_inr": money(left), "reason_codes": codes,
                    "note": f"{int(left)} of {int(qty)} packs are within the limit; a person decides whether to "
                            "credit them or return the claim to be re-lodged"}
        return {"action": "reject", "qty": 0, "credit_inr": 0.0, "reason_codes": codes,
                "note": "Nothing left to claim on this batch"}
    return {"action": "review", "qty": int(qty), "credit_inr": None, "credit_if_approved_inr": money(qty),
            "reason_codes": codes}


def decide(checks: dict[str, CheckResult]) -> str:
    """A hard-rule failure rejects; any other failure or flag goes to a person.
    'clean' still goes to a person in v1: nothing is auto-approved."""
    results = list(checks.values())
    if any(c["outcome"] == "fail" and c["on_fail"] == "reject" for c in results):
        return "reject"
    if any(c["outcome"] in ("fail", "flag") for c in results):  # skip is neither
        return "to_person"
    return "clean"
