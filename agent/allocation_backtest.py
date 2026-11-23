"""Allocation backtest (plan step 5): would the plan's top-ups have prevented the orders that went unfilled?

Chronological replay, no model. For each month-end T with a monthly snapshot (Mar-Aug 2026):
  1. Plan at T with data up to T only: demand.plan(basis, as_of=T) -> top-up per C&F and SKU
     (current shares, FY25 shares), and the old method (refill to 2 months of the SAP outward field).
  2. Deliver the top-up at the start of the next month (assumes the CDC can supply, as the client said).
  3. Serve that month's actual normal orders: non-scheme dispatches + orders cut for lack of stock
     (counted once per stockist and month).
  4. Unfilled = orders above (stock at T + top-up). Valued at PTS.
Returns (current plan): the returning C&F keeps stock at T - return; does that leave it short next month?

Limits: one delivery a month (reality also had deliveries within the month), batches and shelf life are
ignored, scheme orders are left out (the client: not lasting demand). So compare the plans with each other;
"what actually happened" is a reference, not a like-for-like baseline.
"""
from functools import lru_cache

import pandas as pd

from agent import demand
from agent.tools import stock_on_hand, table

STARTS = ("2026-03-31", "2026-04-30", "2026-05-31", "2026-06-30", "2026-07-31", "2026-08-31")
PLANS = ("current", "fy25", "old_report")
KEYS = ["cnf_code", "sku_code"]


def _pts() -> pd.Series:
    return table("sku_master.csv").set_index("sku_code")["pts_inr"].astype(float)


def _snapshot(T: str, col: str) -> pd.Series:
    st = table("cnf_stock_snapshot.csv")
    st = st[st["snapshot_date"] == pd.Timestamp(T)]
    if col == "stock":
        return stock_on_hand(T)
    return st.groupby(KEYS)["avg_monthly_outward_packs"].first().astype(float)


def month_orders(month: pd.Period) -> tuple[pd.Series, pd.Series]:
    """Normal orders in a month (non-scheme dispatched + unmet once) and the unmet part."""
    lines = demand.order_lines()
    w = lines[(lines["month"] == month) & ~lines["is_scheme"]]
    unmet = demand._unmet_once(w)
    return w.groupby(KEYS)["dispatched"].sum().add(unmet, fill_value=0.0), unmet


def top_up(plan: str, T: str) -> pd.Series:
    if plan in ("current", "fy25"):
        return demand.plan(plan, T)["top_up"]
    rep, stock = _snapshot(T, "outward"), _snapshot(T, "stock")
    return (2 * rep - stock.reindex(rep.index).fillna(0.0)).clip(lower=0).round()  # the old allocation screen


@lru_cache(maxsize=1)
def run() -> dict:
    pts = _pts()
    rows, cfa_rows, ret_rows = [], [], []
    for T in STARTS:
        m = pd.Timestamp(T).to_period("M") + 1
        need, actual_unmet = month_orders(m)
        stock = _snapshot(T, "stock")
        idx = need.index.union(stock.index)
        n = need.reindex(idx).fillna(0.0)
        s = stock.reindex(idx).fillna(0.0)
        p = idx.get_level_values("sku_code").map(pts)
        rows.append({"start": T, "month": str(m), "plan": "actual", "orders_inr": float((n * p).sum()),
                     "unfilled_inr": float((actual_unmet.reindex(idx).fillna(0) * p).sum()), "top_up_inr": None})
        for plan in PLANS:
            tu = top_up(plan, T).reindex(idx).fillna(0.0)
            avail = s + tu
            short = (n - avail).clip(lower=0)
            left = (avail - n).clip(lower=0)
            rows.append({"start": T, "month": str(m), "plan": plan, "orders_inr": float((n * p).sum()),
                         "unfilled_inr": float((short * p).sum()), "top_up_inr": float((tu * p).sum()),
                         "left_over_months": float((left * p).sum() / (n * p).sum())})
            for cfa in idx.get_level_values("cnf_code").unique():
                mk = idx.get_level_values("cnf_code") == cfa
                cfa_rows.append({"start": T, "plan": plan, "cnf_code": cfa, "unfilled_inr": float((short[mk] * p[mk]).sum()),
                                 "orders_inr": float((n[mk] * p[mk]).sum())})
        # returns under the current plan: does the returning C&F run short next month?
        for (cfa, sku), r in demand.returns("current", T).iterrows():
            after = s.get((cfa, sku), 0.0) - r["return_qty"]
            need_next = n.get((cfa, sku), 0.0)
            ret_rows.append({"start": T, "cnf_code": cfa, "sku_code": sku, "return_qty": int(r["return_qty"]),
                             "return_inr": float(r["value_inr"]), "stock_after": float(after), "orders_next_month": float(need_next),
                             "short_after_return": float(max(0.0, need_next - after))})
    d = pd.DataFrame(rows)
    totals = d.groupby("plan")[["orders_inr", "unfilled_inr", "top_up_inr"]].sum(min_count=1)
    actual = float(totals.loc["actual", "unfilled_inr"])
    summary = {plan: {"unfilled_inr": round(float(totals.loc[plan, "unfilled_inr"]), 2),
                      "top_up_inr": None if pd.isna(totals.loc[plan, "top_up_inr"]) else round(float(totals.loc[plan, "top_up_inr"]), 2),
                      "fill_rate": round(1 - float(totals.loc[plan, "unfilled_inr"]) / float(totals.loc[plan, "orders_inr"]), 4)}
               for plan in ("actual", *PLANS)}
    c = pd.DataFrame(cfa_rows).groupby(["plan", "cnf_code"])[["unfilled_inr", "orders_inr"]].sum()
    by_cfa = {plan: {cfa: round(float(v), 2) for cfa, v in c.loc[plan, "unfilled_inr"].items()} for plan in PLANS}
    r = pd.DataFrame(ret_rows)
    return {
        "orders_inr": round(float(totals.loc["actual", "orders_inr"]), 2), "actual_unfilled_inr": round(actual, 2),
        "summary": summary, "by_month": d.round(2).to_dict("records"), "unfilled_by_cfa": by_cfa,
        "returns": {"count": int(len(r)), "value_inr": round(float(r["return_inr"].sum()), 2) if len(r) else 0.0,
                    "short_after_return_inr": round(float((r["short_after_return"] * r["sku_code"].map(pts)).sum()), 2) if len(r) else 0.0,
                    "rows": r.round(2).to_dict("records")},
        "limits": __doc__.split("Limits:")[1].strip(),
    }


if __name__ == "__main__":
    out = run()
    print(f"Normal orders, 6 months: Rs {out['orders_inr'] / 1e7:.2f} cr")
    for k, v in out["summary"].items():
        top = "" if v["top_up_inr"] is None else f"; top-up Rs {v['top_up_inr'] / 1e7:.2f} cr"
        print(f"{k:12} unfilled Rs {v['unfilled_inr'] / 1e7:.2f} cr, fill rate {v['fill_rate']:.1%}{top}")
    print("Unfilled by C&F (Rs L):", {p: {c: round(x / 1e5, 1) for c, x in v.items()} for p, v in out["unfilled_by_cfa"].items()})
    r = out["returns"]
    print(f"Returns (current plan): {r['count']} worth Rs {r['value_inr'] / 1e5:.1f} L; left the C&F short next month by Rs {r['short_after_return_inr'] / 1e5:.1f} L")
