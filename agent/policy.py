"""Every policy number the pilot uses, each with the clause it comes from.

Checks and watch views read their thresholds from here and nowhere else, so a change
in policy is one edit, and every result can quote its clause.

Sources: Trade Terms, Schemes and Returns Policy CO-POL-014 v4.2, effective 01 Apr 2025
(02_trade_terms_and_returns_policy.pdf), and the C&F agreement SC-AGR-CF-003 with its
operating procedure (03_cnf_agreement_and_sop.pdf, "CF").
"""
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Rule:
    value: float
    clause: str
    note: str = ""


POLICY = "CO-POL-014"

# --- Claim types and windows (CO-POL-014 5.2) ------------------------------------------
CLAIM_TYPES = ("Near expiry", "Expired", "Breakage in transit", "Short supply")
WINDOW_CLAUSE = "CO-POL-014 5.2"
NEAR_EXPIRY_BEFORE_DAYS = Rule(90, WINDOW_CLAUSE, "Near-expiry claim may be raised up to 90 days before expiry")
EXPIRED_AFTER_DAYS = Rule(90, WINDOW_CLAUSE, "Not accepted under any circumstances over 90 days after expiry")
BREAKAGE_SHORT_DAYS = Rule(7, WINDOW_CLAUSE, "Breakage or short supply within 7 days of invoice")

# Decision D2 (Neha Bansal): early near-expiry claims go to a person in v1, not reject.
EARLY_NEAR_EXPIRY_TO_PERSON = True

# --- Other claim rules -------------------------------------------------------------
DUPLICATE_CLAUSE = "CO-POL-014 5.6; CF Sch 2 2.6.3"  # same stockist, batch and quantity already claimed
SUPPLIED_CLAUSE = "CO-POL-014 5.5, 8.3"  # batch billed to this stockist before the claim date
QUANTITY_CLAUSE = "CO-POL-014 5.5"  # total claimed <= packs supplied, free packs included
INVOICE_REF_CLAUSE = "CO-POL-014 5.3, 5.4"
AM_APPROVAL_CLAUSE = "CO-POL-014 5.4"  # no invoice: purchase ledger + written Area Manager approval
BATCH_CLAUSE = "CO-POL-014 5.3"  # claim lists SKU, batch, expiry and quantity per line
HOME_CFA_CLAUSE = "CO-POL-014 5.1"  # returns received only at the CFA that billed the stock
VALUE_CLAUSE = "CO-POL-014 5.7"  # valued at PTS in force on the claim date
VALUE_TOLERANCE_INR = Rule(1.0, VALUE_CLAUSE, "Rounding tolerance on claim value")
REGISTER_CLAUSE = "CO-POL-014 5.6; CF Sch 2 2.6.1"  # one register entry per claim; settled claims stay settled
BATCH_VERIFIABLE_FROM = date(2023, 10, 1)  # batches made earlier cannot be verified

# --- Dispatch and stock (CF agreement) --------------------------------------------
# Decision D1 confirmed by the policy text: both rules apply. CO-POL-014 7.1: stock billed to a
# stockist must have at least 60% of its shelf life left (the stockist may refuse less), and no
# stock with under 60 days to expiry is dispatched; 7.2 and CF Sch 2 2.3.4: it is blocked.
MIN_SHELF_LIFE_SHARE = Rule(0.60, "CO-POL-014 7.1", "Billed with at least 60% of shelf life left")
BLOCK_DAYS = Rule(60, "CO-POL-014 7.1, 7.2; CF Sch 2 2.3.4", "Under 60 days to expiry: blocked, never picked")
FEFO_CLAUSE = "CF 6.3; Sch 2 2.3"  # pick oldest expiry first; another batch only with a logged override
FEFO_ALERT_SHARE = Rule(0.35, "CF 6.3", "Alert when over 35% of a CFA's packs skip an older batch")
CDC_RETURN_DAYS = Rule(14, "CF Sch 2 2.5", "No CFA-to-CFA transfer: excess returns to the CDC, 10 to 14 days")
CDC_RETURN_APPROVAL = "CF Sch 2 2.5: requested by the Regional Distribution Manager, approved by the Head of Supply Chain"
DESTRUCTION_CLAUSE = "CO-POL-014 5.6, 7.2; CF Sch 2 2.7"  # destroyed monthly under witness, certificate to Finance
FEFO_LOOKAHEAD_DAYS = Rule(90, "Evidence log P3", "An older batch shipped by the same CFA within 90 days was available")
FEFO_WINDOW_MONTHS = Rule(3, "Evidence log P3",
                          "Share measured over 3 months: single months spike at quarter-end scheme loading")
DONOR_KEEP_MONTHS = Rule(2.0, "Allocation (Final Plan)", "Donor CFA keeps two months' cover")
# Allocation bands (ADR 0015). Not in CO-POL-014: proposed planning norms, shown as such.
SHORT_COVER_MONTHS = Rule(1.0, "Allocation norm (proposed)", "Under 1 month of cover: refill")
TARGET_COVER_MONTHS = Rule(2.0, "Allocation norm (proposed)", "Refill up to 2 months of cover")
EXCESS_COVER_MONTHS = Rule(3.0, "Verified analysis", "Above 3 months of cover is excess")

# --- Demand from invoices (docs/allocation-demand-plan.md; client answers 21-22 Nov 2026) ---------
# The SAP report field avg_monthly_outward_packs is not used: the client confirmed it is unreliable.
ALLOC_TARGET_MONTHS = Rule(2.0, "CF Sch 2 2.2", "Top each C&F up to two months of its allocated volume")
SHIPMENT_CAP_MONTHS = Rule(1.2, "CF Sch 2 2.2", "One shipment does not exceed 1.2 months of allocated volume")
NORMAL_MONTHS = Rule(3, "Client 21 Nov", "Normal month: average of the last 3 months with no scheme lines")
SHARE_BASE = ("2024-04-01", "2025-03-31")  # FY25: shares implied by dispatches (client 22 Nov)
SHARE_STEP_LIMIT = Rule(0.05, "Proposed", "A share moves at most 5 points per review (client to confirm)")
RETURN_TRANSIT_DAYS = Rule(14, "Client 22 Nov; CF Sch 2 2.5", "A returned batch must keep 60% shelf life after 14 days in transit")
RETURN_MIN_VALUE_INR = Rule(500000, "Client 22 Nov", "A return is worth making only at Rs 5 lakh or more per SKU")
NOT_MOVING_SOLD_SHARE = Rule(0.05, "Backtest, plan step 3 (22 Nov 2026)",
                             "Watch list: a sellable batch that sold under 5% since the previous snapshot")
ARRIVED_OLD_SHARE = Rule(0.70, "Proposed (plan step 4)",
                         "A batch that first appears at a C&F with under 70% shelf life arrived old from the CDC")
SHORT_DATED_PERIOD = ("2025-10-01", "2026-09-30")  # last four quarters, the verified Rs 6.26 cr
CDC_SUPPLY_ASSUMPTION = "Assumes the CDC can supply: national stock is sufficient (client, 22 Nov 2026)"
SCHEME_WINDOW_MONTHS = (3, 6, 9, 12)  # quarter-end scheme months
SCHEME_WINDOW_FROM_DAY = Rule(22, "CO-POL-014 Annexure B", "Scheme window: the 22nd to month-end of quarter-end months")
TRANSFER_APPROVAL_CLAUSE = CDC_RETURN_APPROVAL

# --- Schemes -----------------------------------------------------------------------
FREE_GOODS_CAP_SHARE = Rule(0.03, "CO-POL-014 4.4", "Free goods in a quarter at most 3% of the quarter's sales")
STOCK_STATEMENT_MONTHS = Rule(2.5, "CO-POL-014 4.5", "No scheme to a stockist holding over 2.5 months of stock")
SCHEME_APPROVAL_CLAUSE = "CO-POL-014 4.3"  # NSM approves; over the cap also the CFO

# --- Service levels ----------------------------------------------------------------
CLAIM_SETTLE_DAYS = Rule(30, "CO-POL-014 5.6", "Credit note within 30 days of receipt of the claim")
CLAIM_VERIFY_WORKING_DAYS = Rule(10, "CO-POL-014 5.6; CF Sch 4", "Physical verification within 10 working days")

# --- Reason codes: every reject or review names one, so outcomes can be counted --------
REASON_CODE = {
    "chk_duplicate": "DUPLICATE",
    "chk_window": "OUT_OF_WINDOW",
    "chk_supplied": "NOT_SUPPLIED",
    "chk_quantity": "OVER_QUANTITY",
    "chk_invoice_ref": "NO_INVOICE_MATCH",
    "chk_batch": "BATCH_MISMATCH",
    "chk_value": "VALUE_MISMATCH",
    "chk_cfa": "WRONG_CFA",
}

# --- What the stockist must send for each gap (letters quote these) --------------------
NEEDED = {
    "chk_invoice_ref": "the original Pfizer invoice number; if it is not available, the C&F will check your "
                       "purchase ledger for this batch with written approval from your Area Manager (CO-POL-014 5.4)",
    "chk_batch": "the batch number and expiry exactly as printed on the pack (CO-POL-014 5.3)",
    "chk_quantity": "the quantity, which cannot exceed the packs of this batch invoiced to you, free packs "
                    "included (CO-POL-014 5.5)",
    "chk_value": "no action: the claim is valued at quantity x PTS on the claim date (CO-POL-014 5.7)",
    "chk_cfa": "the return to be sent to the CFA that billed the stock (CO-POL-014 5.1)",
    "missing_batch": "the batch number printed on the pack (CO-POL-014 5.3)",
    "missing_qty": "the quantity in packs for each batch (CO-POL-014 5.3)",
    "missing_stockist": "the claim from your registered mailbox, so we can identify your account",
}

# --- Emails that are not claims: who handles them (code, not a model) ------------------
FORWARD_RULES = (
    (r"\bmrp\b|price|dpco|nppa", "Commercial Finance (price revisions, CO-POL-014 6)"),
    (r"scheme|\bfoc\b|free goods|offer", "Sales Operations (trade schemes, CO-POL-014 4)"),
    (r"transit|deliver|dispatch|delay|took \d+ days|late", "Supply Chain, CFA operations"),
    (r"credit limit|payment|outstanding|ledger", "Commercial Finance (credit, CO-POL-014 3)"),
)

# --- Data ---------------------------------------------------------------------------
SNAPSHOT_DATE = date(2026, 9, 30)  # cnf_stock_snapshot latest date; the extracts end here
