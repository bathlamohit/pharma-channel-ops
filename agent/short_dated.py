"""Dispatches under 60% shelf life: every one flagged, with where it piles up and why (plan step 4).

CO-POL-014 7.1: stock billed to a stockist must have at least 60% of its shelf life left; a stockist
may refuse less. The client: there are no approved exceptions, so flag every one; don't block, because
it may go out with the stockist's agreement; find where it is piling up, and why.

Plain pandas, no model. Period: the last four quarters (the verified Rs 6.26 cr). For each invoice line:
  shelf life left at dispatch = (batch expiry - invoice date) / (shelf life months x 30.44 days)
Likely reasons (a line can have several; each is a check on data available at the time):
  arrived old       the batch first appeared at this C&F (first dispatch or first snapshot) with under
                    70% shelf life: it came from the CDC already aged (70% is a proposed cut-off)
  too much stock    at the snapshot before the dispatch the C&F held over 2 months of the product
                    against its normal demand (agent/demand.py)
  out of order      the C&F's share of packs picked out of order was over 35% in the months before
                    (CF 6.3); newer batches went first and this one aged
  scheme push       the line carries a scheme code (quarter-end loading of older stock)
"""
import copy
from functools import lru_cache

import numpy as np
import pandas as pd

from agent import demand, policy
from agent.tools import cite, table, stock_on_hand

DAYS_PER_MONTH = 30.44
REASONS = {
    "arrived_old": "Arrived old from the CDC",
    "too_much": "Too much stock at the C&F",
    "out_of_order": "Picked out of order",
    "scheme": "Scheme push",
    "none": "No clear reason in the data",
}


@lru_cache(maxsize=1)
def lines() -> pd.DataFrame:
    """Every invoice line in the period billed with under 60% shelf life, with its likely reasons."""
    from agent.watch import fefo_share
    s = table("primary_sales.csv").copy()
    for c in ("invoiced_qty", "free_qty", "net_value_inr"):
        s[c] = pd.to_numeric(s[c], errors="coerce").fillna(0.0)
    s["packs"] = s["invoiced_qty"] + s["free_qty"]
    b = table("batch_master.csv")[["batch_no", "expiry_date"]]
    k = table("sku_master.csv")[["sku_code", "shelf_life_months", "product_description"]].copy()
    k["shelf_life_months"] = k["shelf_life_months"].astype(float)
    s = s[s["batch_no"] != ""].merge(b, on="batch_no", how="left").merge(k, on="sku_code")
    s["days_left"] = (s["expiry_date"] - s["invoice_date"]).dt.days
    s["shelf_share"] = s["days_left"] / (s["shelf_life_months"] * DAYS_PER_MONTH)

    # first time each C&F held or dispatched each batch (all history, not only the period)
    st = table("cnf_stock_snapshot.csv")
    st = st[st["batch_no"] != ""]
    first = pd.concat([s.groupby(["cnf_code", "batch_no"])["invoice_date"].min(),
                       st.groupby(["cnf_code", "batch_no"])["snapshot_date"].min()], axis=1).min(axis=1)

    a, z = policy.SHORT_DATED_PERIOD
    d = s[s["invoice_date"].between(a, z) & (s["shelf_share"] < policy.MIN_SHELF_LIFE_SHARE.value)].copy()
    d["first_seen"] = [first.get((c, n)) for c, n in zip(d["cnf_code"], d["batch_no"])]
    d["share_first_seen"] = ((d["expiry_date"] - d["first_seen"]).dt.days / (d["shelf_life_months"] * DAYS_PER_MONTH)).round(3)

    snaps = np.sort(st["snapshot_date"].unique())
    pos = np.searchsorted(snaps, d["invoice_date"].values, side="left")  # latest snapshot strictly before
    d["prev_snapshot"] = pd.Series(np.where(pos > 0, snaps[np.maximum(pos - 1, 0)], np.datetime64("NaT", "ns")),
                                   index=d.index, dtype="datetime64[ns]")
    cover = {}
    for p in d["prev_snapshot"].dropna().unique():
        p = pd.Timestamp(p)
        stock = stock_on_hand(p)
        normal = demand.demand(str(pd.Timestamp(p).date()))["normal_month"]
        cover[p] = stock / normal.reindex(stock.index).where(lambda v: v > 0)
    d["cover_before"] = [None if pd.isna(p) else cover[pd.Timestamp(p)].get((c, k_)) for p, c, k_ in zip(d["prev_snapshot"], d["cnf_code"], d["sku_code"])]
    d["cover_before"] = pd.to_numeric(d["cover_before"], errors="coerce").round(2)

    share = fefo_share()

    memo = {}

    def out_of_order(cfa, m):  # the latest rolling share up to the month before the invoice
        if (cfa, m) not in memo:
            x = share[cfa].dropna()
            x = x[x.index <= m]
            memo[cfa, m] = round(float(x.iloc[-1]), 3) if len(x) else 0.0
        return memo[cfa, m]

    before = d["invoice_date"].dt.to_period("M") - 1
    d["out_of_order_share"] = [out_of_order(c, m) for c, m in zip(d["cnf_code"], before)]
    d["arrived_old"] = d["share_first_seen"] < policy.ARRIVED_OLD_SHARE.value
    d["too_much"] = d["cover_before"] > policy.ALLOC_TARGET_MONTHS.value
    d["out_of_order"] = d["out_of_order_share"] > policy.FEFO_ALERT_SHARE.value
    d["scheme"] = d["scheme_code"] != ""
    keys = ["arrived_old", "too_much", "out_of_order", "scheme"]
    flags = d[keys].to_numpy(dtype=bool)
    d["reasons"] = [[k_ for k_, f in zip(keys, row) if f] or ["none"] for row in flags]
    claims = table("expiry_claims.csv")
    claimed = set(zip(claims.loc[claims["status"] != "Rejected", "stockist_code"], claims.loc[claims["status"] != "Rejected", "batch_no"]))
    d["claimed_later"] = [(st_, n) in claimed for st_, n in zip(d["stockist_code"], d["batch_no"])]
    names = table("stockist_master.csv").set_index("stockist_code")["stockist_name"]
    d["stockist_name"] = d["stockist_code"].map(names)
    d["cnf_city"] = d["cnf_code"].map(dict(zip(st["cnf_code"], st["cnf_city"])))
    return d.sort_values(["invoice_date", "invoice_no"]).reset_index(drop=True)


def _reason_totals(d: pd.DataFrame) -> list[dict]:
    out = []
    for k_, label in REASONS.items():
        m = d["reasons"].map(lambda r: k_ in r)
        out.append({"reason": k_, "label": label, "lines": int(m.sum()), "value_inr": round(float(d.loc[m, "net_value_inr"].sum()), 2)})
    return out


@lru_cache(maxsize=1)
def _summary() -> dict:
    d = lines()
    a, z = policy.SHORT_DATED_PERIOD
    s = table("primary_sales.csv")
    period = s[s["invoice_date"].between(a, z)]
    disp = period.assign(v=pd.to_numeric(period["net_value_inr"], errors="coerce")).groupby("cnf_code")["v"].sum()
    cfas = []
    for (cfa, city), g in d.groupby(["cnf_code", "cnf_city"]):
        reasons = _reason_totals(g)
        main = max((r for r in reasons if r["reason"] != "none"), key=lambda r: r["value_inr"])
        cfas.append({"cnf_code": cfa, "cnf_city": city, "lines": int(len(g)), "value_inr": round(float(g["net_value_inr"].sum()), 2),
                     "share_of_dispatch": round(float(g["net_value_inr"].sum() / disp[cfa]), 4), "stockists": int(g["stockist_code"].nunique()),
                     "batches": int(g["batch_no"].nunique()), "main_reason": main["label"],
                     "main_reason_share": round(main["value_inr"] / float(g["net_value_inr"].sum()), 3), "reasons": reasons})
    prod = d.groupby(["sku_code", "product_description"]).agg(lines=("invoice_no", "size"), value_inr=("net_value_inr", "sum"),
                                                              batches=("batch_no", "nunique"), cfas=("cnf_code", "nunique")).reset_index()
    stk = d.groupby(["stockist_code", "stockist_name", "cnf_code"]).agg(lines=("invoice_no", "size"), value_inr=("net_value_inr", "sum"),
                                                                       claimed=("claimed_later", "sum")).reset_index()
    bat = d.groupby(["cnf_code", "cnf_city", "batch_no", "product_description"]).agg(
        lines=("invoice_no", "size"), value_inr=("net_value_inr", "sum"), share_first_seen=("share_first_seen", "first"),
        expiry=("expiry_date", "first")).reset_index()
    month = d.groupby(d["invoice_date"].dt.to_period("M"))["net_value_inr"].sum()
    return {
        "period": {"from": a, "to": z}, "lines": int(len(d)), "value_inr": round(float(d["net_value_inr"].sum()), 2),
        "under_60_days": int((d["days_left"] < policy.BLOCK_DAYS.value).sum()),
        "stockists": int(d["stockist_code"].nunique()), "batches": int(d["batch_no"].nunique()),
        "claimed_later_value_inr": round(float(d.loc[d["claimed_later"], "net_value_inr"].sum()), 2),
        "reasons": _reason_totals(d), "cfas": sorted(cfas, key=lambda c: -c["value_inr"]),
        "products": [{**r, "value_inr": round(float(r["value_inr"]), 2)} for r in prod.sort_values("value_inr", ascending=False).head(10).to_dict("records")],
        "stockists_top": [{**r, "value_inr": round(float(r["value_inr"]), 2), "claimed": int(r["claimed"])}
                          for r in stk.sort_values("value_inr", ascending=False).head(10).to_dict("records")],
        "batches_top": [{**r, "value_inr": round(float(r["value_inr"]), 2), "expiry": r["expiry"].strftime("%Y-%m-%d")}
                        for r in bat.sort_values("value_inr", ascending=False).head(10).to_dict("records")],
        "by_month": {str(m): round(float(v), 2) for m, v in month.items()},
        "rule": f"CO-POL-014 7.1: bill with at least 60% of shelf life; the stockist may refuse less. No approved "
                f"exceptions (client), so every one is flagged; not blocked, it may go with the stockist's agreement.",
        "reason_note": f"'Arrived old' uses a proposed cut-off: first seen at the C&F with under "
                       f"{policy.ARRIVED_OLD_SHARE.value:.0%} shelf life.",
    }


def summary() -> dict:
    return copy.deepcopy(_summary())


def for_cfa(cfa: str, reason: str | None = None, offset: int = 0, limit: int = 50) -> dict:
    """One C&F's flagged lines (newest first), optionally by reason, a page at a time, with citations."""
    d = lines()
    d = d[d["cnf_code"] == cfa]
    if d.empty:
        raise ValueError(f"No short-dated dispatches for {cfa!r}")
    if reason:
        if reason not in REASONS:
            raise ValueError(f"reason is one of {list(REASONS)}")
        d = d[d["reasons"].map(lambda r: reason in r)]
    d = d.sort_values(["invoice_date", "invoice_no"], ascending=False)
    page = d.iloc[offset:offset + limit]
    rows = [{"invoice_no": r.invoice_no, "invoice_date": r.invoice_date.strftime("%Y-%m-%d"), "stockist_code": r.stockist_code,
             "stockist_name": r.stockist_name, "sku_code": r.sku_code, "product": r.product_description, "batch_no": r.batch_no,
             "packs": int(r.packs), "value_inr": round(float(r.net_value_inr), 2), "shelf_share": round(float(r.shelf_share), 3),
             "days_left": int(r.days_left), "share_first_seen": None if pd.isna(r.share_first_seen) else float(r.share_first_seen),
             "cover_before": None if pd.isna(r.cover_before) else float(r.cover_before), "out_of_order_share": float(r.out_of_order_share),
             "scheme_code": r.scheme_code, "reasons": [REASONS[k_] for k_ in r.reasons], "claimed_later": bool(r.claimed_later),
             "src_line": int(r.src_line)} for r in page.itertuples()]
    return {"cnf_code": cfa, "total": int(len(d)), "offset": offset, "rows": rows,
            "value_inr": round(float(d["net_value_inr"].sum()), 2),
            "citations": [cite("primary_sales.csv", d)] if len(d) else []}
