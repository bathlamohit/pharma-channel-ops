"""Back-test the hard rules over the claims register, using the SAME rule functions the
live claim path runs (rules.chk_duplicate, rules.chk_window). No model, no graph.

    python -m agent.backtest

Hard rules (each claim counted once):
  - same stockist, batch and quantity already claimed (earlier, not rejected)
  - raised over 90 days after the batch expired (any claim type)
  - breakage or short supply raised over 7 days after the referenced invoice

Verified figures (Final Plan, "Outcome and money"), reproduced with fix_prefix=False:
  credited Oct 2025 - Sep 2026 breaking a hard rule: 181 claims, Rs 21.9 L
  pending claims breaking a hard rule:                38 claims, Rs 7.25 L
  credited twice over the full 30 months:              61 claims, Rs 11.2 L
With fix_prefix=True (INV- refs read as INV/), 4 more credited and 3 more pending claims
are caught: Rs 22.12 L and Rs 7.37 L. That is the live behaviour.
"""
from dataclasses import dataclass
from datetime import date

import pandas as pd

from agent import rules
from agent.tools import cite, norm_invoice, table

HARD_CHECKS = (rules.chk_duplicate, rules.chk_window)


@dataclass
class BacktestResult:
    claims: pd.DataFrame  # one row per claim: claim_no, status, value, failed checks, details

    def total(self, status: str, start: date | None = None, end: date | None = None) -> tuple[int, float]:
        df = self.claims[(self.claims["status"] == status) & self.claims["hard_fail"]]
        if start:
            df = df[df["claim_date"] >= pd.Timestamp(start)]
        if end:
            df = df[df["claim_date"] <= pd.Timestamp(end)]
        return len(df), float(df["claim_value_inr"].sum())


def _index(df: pd.DataFrame, keys: list[str], cols: list[str]) -> dict:
    """Plain-dict index: key -> list of row dicts (much faster than pandas groupby here)."""
    out: dict = {}
    for row in df[cols].to_dict("records"):
        k = tuple(row[c] for c in keys) if len(keys) > 1 else row[keys[0]]
        out.setdefault(k, []).append(row)
    return out


def _records_index(fix_prefix: bool):
    claims = table("expiry_claims.csv")
    by_pair = _index(claims, ["stockist_code", "batch_no"],
                     ["src_line", "claim_no", "claim_date", "stockist_code", "batch_no", "qty_claimed", "status"])
    batches = _index(table("batch_master.csv"), ["batch_no"], ["src_line", "batch_no", "sku_code", "mfg_date", "expiry_date"])
    invoices = _index(table("primary_sales.csv"), ["invoice_no"],
                      ["src_line", "invoice_no", "invoice_date", "stockist_code", "batch_no"])

    missing = {"found": False, "rows": [], "citation": None}
    cache: dict = {}

    def rec(file: str, index: dict, key) -> dict:
        """Same shape tools.* returns, built once per key."""
        if (file, key) not in cache:
            rows = index.get(key)
            cache[file, key] = missing if not rows else {
                "found": True, "rows": rows, "citation": cite(file, pd.DataFrame({"src_line": [r["src_line"] for r in rows]}))}
        return cache[file, key]

    def records(row: dict) -> dict:
        ref = norm_invoice(row["original_invoice_ref"], fix_prefix) if row["original_invoice_ref"] else None
        return {
            "prior_claims": rec("expiry_claims.csv", by_pair, (row["stockist_code"], row["batch_no"])),
            "batch": rec("batch_master.csv", batches, row["batch_no"]),
            "invoice": rec("primary_sales.csv", invoices, ref),
        }

    return claims, records


def run_backtest(fix_prefix: bool = True) -> BacktestResult:
    claims, records = _records_index(fix_prefix)
    out = []
    for row in claims.to_dict("records"):
        claim = {**row, "invoice_ref": row["original_invoice_ref"]}
        results = [check(claim, records(row)) for check in HARD_CHECKS]
        failed = [r for r in results if r["outcome"] == "fail" and r["on_fail"] == "reject"]
        out.append({"claim_no": row["claim_no"], "claim_date": row["claim_date"], "status": row["status"],
                    "stockist_code": row["stockist_code"], "src_line": row["src_line"],
                    "claim_value_inr": float(row["claim_value_inr"] or 0),
                    "hard_fail": bool(failed), "failed": ",".join(r["check"] for r in failed),
                    "detail": "; ".join(r["detail"] for r in failed)})
    return BacktestResult(pd.DataFrame(out))


def credited_twice() -> tuple[int, float, pd.DataFrame]:
    """Credited claims that repeat an earlier non-rejected claim, over the full 30 months."""
    c = table("expiry_claims.csv").sort_values(["claim_date", "claim_no"])
    live = c[c["status"] != rules.REJECTED]
    dup = live[live.duplicated(["stockist_code", "batch_no", "qty_claimed"], keep="first")]
    dup = dup[dup["status"] == "Credited"]
    return len(dup), float(dup["claim_value_inr"].astype(float).sum()), dup


def main() -> None:
    year = (date(2025, 10, 1), date(2026, 9, 30))
    for fix in (False, True):
        bt = run_backtest(fix_prefix=fix)
        n, v = bt.total("Credited", *year)
        pn, pv = bt.total("Pending")
        label = "INV- refs fixed (live)" if fix else "refs as written (verified)"
        print(f"{label:28} credited last 4 quarters: {n} claims Rs {v / 1e5:.2f} L | pending: {pn} claims Rs {pv / 1e5:.2f} L")
    n, v, _ = credited_twice()
    print(f"{'credited twice, 30 months':28} {n} claims Rs {v / 1e5:.2f} L")


if __name__ == "__main__":
    main()
