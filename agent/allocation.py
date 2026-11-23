"""Allocation plan on demand from invoices (plan step 2; docs/allocation-demand-plan.md).

Plain pandas, no model. Demand comes only from agent/demand.py (never the SAP outward field).
Each C&F is topped up from the CDC to two months of its allocated volume, at most 1.2 months in
one shipment (CF Sch 2 2.2). Allocated volume = national normal demand x the C&F's share.

Shares: 'current' (share of real need now; our recommendation, awaiting the client's approval)
or 'fy25' (the client's instruction until then). Every view takes the basis; the screen shows
current with FY25 beside it.

Statuses per C&F and product:
  out of stock   nothing on hand, it has allocated volume    urgent top-up
  below target   under 2 months                               top-up this month
  on target      at 2 months                                  none
  excess         over 2 months                                return to the CDC if the client's
                                                              rules allow (60% shelf life after
                                                              14 days in transit; >= Rs 5 lakh per SKU),
                                                              else hold replenishment
Top-ups assume the CDC can supply (client, 22 Nov 2026).
"""
import copy
from functools import lru_cache

import pandas as pd

from agent import demand, policy
from agent.tools import cite, table
from agent.watch import excess_scheme_claims, free_goods_vs_cap, scheme_claim_rates

BASES = ("current", "fy25")
ORDER = {"out of stock": 0, "below target": 1, "excess": 2, "on target": 3}


def _check(basis: str) -> str:
    if basis not in BASES:
        raise ValueError(f"basis is one of {BASES}")
    return basis


def _names() -> tuple[pd.Series, dict]:
    sku = table("sku_master.csv").set_index("sku_code")["product_description"]
    st = table("cnf_stock_snapshot.csv")
    return sku, dict(zip(st["cnf_code"], st["cnf_city"]))


@lru_cache(maxsize=2)
def products(basis: str = "current") -> pd.DataFrame:
    """One row per C&F and product with demand, share, allocated volume, status, top-up and excess."""
    p = demand.plan(_check(basis)).reset_index()
    p = p[p["status"] != "none"].copy()
    sku, city = _names()
    p["product"] = p["sku_code"].map(sku)
    p["cnf_city"] = p["cnf_code"].map(city)
    target = policy.ALLOC_TARGET_MONTHS.value
    p["excess_packs"] = (p["stock"] - target * p["allocated_month"]).clip(lower=0).round()
    ret = demand.returns(basis).reset_index()
    p = p.merge(ret[["cnf_code", "sku_code", "return_qty", "value_inr"]].rename(columns={"value_inr": "return_inr"}),
                on=["cnf_code", "sku_code"], how="left")
    p[["return_qty", "return_inr"]] = p[["return_qty", "return_inr"]].fillna(0.0)
    for c in ("stock", "allocated_month", "top_up", "excess_packs", "real_need_month", "normal_month", "unmet_month"):
        p[f"{c}_inr"] = (p[c] * p["pts_inr"]).round(2)
    return p


def _advice(r: pd.Series) -> dict:
    a, need = r["allocated_month"], r["real_need_month"]
    cut = f" (+{int(round(r['unmet_month'])):,} cut for lack of stock)" if r["unmet_month"] >= 1 else ""
    why_need = f"allocated {int(round(a)):,} packs a month; normal demand here {int(round(r['normal_month'])):,}{cut}"
    if r["status"] in ("out of stock", "below target"):
        head = "Out of stock" if r["status"] == "out of stock" else f"{r['months_of_stock']:.2f} months of stock"
        return {"title": "Top up from the CDC", "action": "top_up", "why": f"{head}; {why_need}",
                "do": f"Send {int(r['top_up']):,} packs this month (to 2 months; at most 1.2 months in one shipment). "
                      f"{policy.CDC_SUPPLY_ASSUMPTION}",
                "clause": policy.ALLOC_TARGET_MONTHS.clause}
    if r["status"] == "excess":
        months = "no allocated volume" if a <= 0 else f"{r['months_of_stock']:.2f} months of stock"
        if r["return_qty"] > 0:
            do = (f"Return {int(r['return_qty']):,} packs (Rs {r['return_inr'] / 1e5:.1f} L) to the CDC: only batches that keep "
                  "60% shelf life after 14 days in transit. Send nothing more until stock is under 2 months.")
        else:
            do = ("Send nothing more until stock is under 2 months. No return: the excess is under Rs 5 lakh, or its batches "
                  "would fall under 60% shelf life in transit")
        return {"title": "Too much stock", "action": "excess", "why": f"{months} against a 2-month target; {why_need}",
                "do": do, "clause": f"{policy.ALLOC_TARGET_MONTHS.clause}; {policy.RETURN_MIN_VALUE_INR.clause}"}
    return {"title": "On target", "action": "none", "why": f"{r['months_of_stock']:.2f} months of stock; {why_need}",
            "do": "No action", "clause": policy.ALLOC_TARGET_MONTHS.clause}


def _row(r: pd.Series) -> dict:
    out = {k: (None if pd.isna(r[k]) else (float(r[k]) if isinstance(r[k], (float, int)) else r[k])) for k in (
        "cnf_code", "cnf_city", "sku_code", "product", "status", "stock", "normal_month", "unmet_month", "real_need_month",
        "share", "allocated_month", "months_of_stock", "top_up", "excess_packs", "return_qty", "stock_inr",
        "allocated_month_inr", "top_up_inr", "excess_packs_inr", "return_inr")}
    for k in ("stock", "top_up", "excess_packs", "return_qty"):
        out[k] = int(round(out[k] or 0))
    for k in ("normal_month", "unmet_month", "real_need_month", "allocated_month"):
        out[k] = round(out[k] or 0, 1)
    out["share"] = round(out["share"] or 0, 4)
    return {**out, **_advice(r)}


@lru_cache(maxsize=2)
def _overview(basis: str) -> dict:
    p = products(basis)
    other = products("fy25" if basis == "current" else "current")
    shares = demand.share_table()
    u = demand.unfilled().groupby(level="cnf_code")[["unmet_inr", "scheme_cut_inr"]].sum()
    cards = []
    for (cfa, city), g in p.groupby(["cnf_code", "cnf_city"]):
        o = other[other["cnf_code"] == cfa]
        alloc = g["allocated_month_inr"].sum()
        st = g["status"].value_counts()
        cards.append({
            "cnf_code": cfa, "cnf_city": city,
            "cover_months": round(float(g["stock_inr"].sum() / alloc), 2) if alloc else None,
            "cover_months_other_basis": round(float(o["stock_inr"].sum() / o["allocated_month_inr"].sum()), 2),
            "cover_on_own_demand": round(float(g["stock_inr"].sum() / g["normal_month_inr"].sum()), 2),
            "share_fy25": round(float(shares.loc[cfa, "fy25_share"]), 4),
            "share_current": round(float(shares.loc[cfa, "current_share"]), 4),
            "share_change_pts": round(float(shares.loc[cfa, "share_change_pts"]), 1),
            "gap_on_fy25_inr": round(float(shares.loc[cfa, "gap_on_fy25_inr"]), 2),
            "out_of_stock": int(st.get("out of stock", 0)), "below_target": int(st.get("below target", 0)),
            "on_target": int(st.get("on target", 0)), "excess": int(st.get("excess", 0)),
            "top_up_inr": round(float(g["top_up_inr"].sum()), 2), "excess_inr": round(float(g["excess_packs_inr"].sum()), 2),
            "return_inr": round(float(g["return_inr"].sum()), 2),
            "unfilled_6m_inr": round(float(u["unmet_inr"].get(cfa, 0.0)), 2),
        })
    nat_alloc = p["allocated_month_inr"].sum()
    uu = demand.unfilled()
    return {
        "as_of": policy.SNAPSHOT_DATE.isoformat(), "basis": basis,
        "normal_months": [str(m) for m in demand.normal_months()],
        "national": {
            "cover_months": round(float(p["stock_inr"].sum() / nat_alloc), 2),
            "allocated_month_inr": round(float(nat_alloc), 2),
            "top_up_inr": round(float(p["top_up_inr"].sum()), 2),
            "top_up_lines": int((p["top_up"] > 0).sum()),
            "return_inr": round(float(p["return_inr"].sum()), 2), "return_lines": int((p["return_qty"] > 0).sum()),
            "out_of_stock": int((p["status"] == "out of stock").sum()),
            "unfilled_6m_inr": round(float(uu["unmet_inr"].sum()), 2),
            "scheme_cut_6m_inr": round(float(uu["scheme_cut_inr"].sum()), 2),
        },
        "cards": sorted(cards, key=lambda c: c["cover_months"] if c["cover_months"] is not None else 99),
        "rules": {"target_months": policy.ALLOC_TARGET_MONTHS.value, "shipment_cap_months": policy.SHIPMENT_CAP_MONTHS.value,
                  "target_clause": policy.ALLOC_TARGET_MONTHS.clause, "return_min_inr": policy.RETURN_MIN_VALUE_INR.value,
                  "return_transit_days": policy.RETURN_TRANSIT_DAYS.value, "share_step_limit": policy.SHARE_STEP_LIMIT.value},
        "assumptions": [
            "Demand comes from invoices (primary_sales). The SAP 'average monthly outward' field is not used: the client "
            "confirmed it is unreliable.",
            "Allocated volume = national normal demand (non-scheme dispatches) x share. The national forecast and "
            "shares are not available (client, 22 Nov).",
            "Current shares = each C&F's share of real need now; recommended to the client, awaiting approval. "
            "FY25 shares are the client's instruction until then.",
            policy.CDC_SUPPLY_ASSUMPTION + ".",
        ],
    }


@lru_cache(maxsize=16)
def _plan(cfa: str, basis: str) -> dict:
    p = products(basis)
    mine = p[p["cnf_code"] == cfa]
    if mine.empty:
        raise ValueError(f"No stock or demand for {cfa!r}")
    rows = [_row(r) for _, r in mine.iterrows()]
    rows.sort(key=lambda x: (ORDER[x["status"]], -(x["top_up_inr"] or 0), -(x["excess_packs_inr"] or 0)))
    u = demand.unfilled()
    u = u[u.index.get_level_values("cnf_code") == cfa].reset_index()
    sku, _ = _names()
    by_product = [{"sku_code": r.sku_code, "product": sku.get(r.sku_code, r.sku_code), "unfilled_inr": float(r.unmet_inr),
                   "scheme_cut_inr": float(r.scheme_cut_inr), "cut_lines": int(r.cut_lines)}
                  for r in u.sort_values("unmet_inr", ascending=False).itertuples() if r.unmet_inr > 0 or r.scheme_cut_inr > 0][:15]
    st = table("cnf_stock_snapshot.csv")
    snap = st[(st["snapshot_date"] == pd.Timestamp(policy.SNAPSHOT_DATE)) & (st["cnf_code"] == cfa)]
    lines = demand.order_lines()
    used = lines[(lines["cnf_code"] == cfa) & lines["month"].isin(demand.normal_months())]
    return {"cnf_code": cfa, "cnf_city": mine["cnf_city"].iloc[0], "basis": basis, "products": rows,
            "unfilled": {"total_inr": round(float(u["unmet_inr"].sum()), 2),
                         "scheme_cut_inr": round(float(u["scheme_cut_inr"].sum()), 2), "by_product": by_product},
            "citations": [cite("cnf_stock_snapshot.csv", snap),
                          cite("primary_sales.csv", pd.DataFrame({"src_line": [n for ls in used["src_lines"] for n in ls]}))]}


@lru_cache(maxsize=2)
def _topups(basis: str) -> dict:
    """The monthly replenishment from the CDC: what each C&F needs this month."""
    p = products(basis)
    t = p[p["top_up"] > 0]
    out = []
    for (cfa, city), g in t.groupby(["cnf_code", "cnf_city"]):
        rows = [_row(r) for _, r in g.iterrows()]
        rows.sort(key=lambda x: (ORDER[x["status"]], -x["top_up_inr"]))
        out.append({"cnf_code": cfa, "cnf_city": city, "lines": rows, "packs": int(g["top_up"].sum()),
                    "value_inr": round(float(g["top_up_inr"].sum()), 2), "out_of_stock": int((g["status"] == "out of stock").sum())})
    out.sort(key=lambda x: -x["value_inr"])
    return {"basis": basis, "assumption": policy.CDC_SUPPLY_ASSUMPTION, "cfas": out,
            "total_inr": round(float(t["top_up_inr"].sum()), 2), "lines": int(len(t))}


@lru_cache(maxsize=2)
def _returns(basis: str) -> dict:
    """Returns to the CDC under the client's rules, with the batches that qualify."""
    from agent import stock
    r = demand.returns(basis).reset_index()
    sku, city = _names()
    b = stock.batches()
    after = b["days_left"] - policy.RETURN_TRANSIT_DAYS.value
    ok = b[(after / (b["shelf_life_months"] * 30.44) >= policy.MIN_SHELF_LIFE_SHARE.value) & (after >= policy.BLOCK_DAYS.value)]
    rows = []
    for x in r.itertuples():
        bb = ok[(ok["cnf_code"] == x.cnf_code) & (ok["sku_code"] == x.sku_code)].sort_values("expiry_date")
        rows.append({"cnf_code": x.cnf_code, "cnf_city": city.get(x.cnf_code), "sku_code": x.sku_code,
                     "product": sku.get(x.sku_code), "return_qty": int(x.return_qty), "value_inr": float(x.value_inr),
                     "spare_packs": int(round(x.spare)),
                     "batches": [{"batch_no": y.batch_no, "expiry_date": y.expiry_date.strftime("%Y-%m-%d"), "qty": int(y.qty),
                                  "shelf_after_transit": round(float((y.days_left - policy.RETURN_TRANSIT_DAYS.value)
                                                                     / (y.shelf_life_months * 30.44)), 3)}
                                 for y in bb.itertuples()]})
    return {"basis": basis, "returns": rows, "total_inr": round(sum(x["value_inr"] for x in rows), 2),
            "rules": [f"Only batches that keep {policy.MIN_SHELF_LIFE_SHARE.value:.0%} shelf life and "
                      f"{int(policy.BLOCK_DAYS.value)} days after {int(policy.RETURN_TRANSIT_DAYS.value)} days in transit",
                      f"At least Rs {policy.RETURN_MIN_VALUE_INR.value / 1e5:.0f} lakh per SKU (client, 22 Nov)",
                      "Requested by the Regional Distribution Manager, approved by the Head of Supply Chain (CF Sch 2 2.5)"]}


@lru_cache(maxsize=1)
def _shares() -> dict:
    """FY25 against current shares per C&F, and the products whose share moved most."""
    t = demand.share_table()
    _, city = _names()
    fy = demand.fy25_shares()
    cur = demand.current_shares()
    sku, _ = _names()
    d = pd.concat([fy, cur], axis=1).fillna(0.0)
    d["change"] = d["current_share"] - d["fy25_share"]
    top = d.reindex(d["change"].abs().sort_values(ascending=False).index).head(12).reset_index()
    return {
        "cfas": [{"cnf_code": cfa, "cnf_city": city.get(cfa), "fy25_share": round(float(r.fy25_share), 4),
                  "current_share": round(float(r.current_share), 4), "change_pts": round(float(r.share_change_pts), 1),
                  "fy25_allocated_inr": round(float(r.fy25_allocated_inr), 2), "real_need_inr": round(float(r.real_need_inr), 2),
                  "gap_on_fy25_inr": round(float(r.gap_on_fy25_inr), 2),
                  "over_step_limit": bool(abs(r.share_change_pts) > policy.SHARE_STEP_LIMIT.value * 100)}
                 for cfa, r in t.iterrows()],
        "largest_product_changes": [{"cnf_code": r.cnf_code, "cnf_city": city.get(r.cnf_code), "sku_code": r.sku_code,
                                     "product": sku.get(r.sku_code), "fy25_share": round(float(r.fy25_share), 4),
                                     "current_share": round(float(r.current_share), 4)} for r in top.itertuples()],
        "step_limit_pts": policy.SHARE_STEP_LIMIT.value * 100,
        "status": "Recommended to the client; awaiting approval (mid-year change via the Regional Distribution Manager, CF Sch 2 2.2)",
    }


@lru_cache(maxsize=1)
def _restatement() -> list[dict]:
    r = demand.restatement()
    return [{k: (None if (isinstance(v, float) and pd.isna(v)) else v) for k, v in row.items()} for row in r.to_dict("records")]


@lru_cache(maxsize=1)
def _schemes() -> dict:
    """For the NSM and CFO: scheme products' claim rate, and free goods against the 3% cap."""
    start = pd.Timestamp(policy.SNAPSHOT_DATE) - pd.DateOffset(years=1) + pd.Timedelta(days=1)
    end = pd.Timestamp(policy.SNAPSHOT_DATE)
    rates = scheme_claim_rates(start, end)
    cap = free_goods_vs_cap()
    quarters = [{"quarter": f"FY{str(q.qyear)[2:]} Q{q.quarter}", "free_goods_inr": round(float(r.free_goods_inr), 2),
                 "sales_inr": round(float(r.sales_inr), 2), "share": round(float(r.share), 4),
                 "over_cap_inr": round(float(r.over_cap_inr), 2)} for q, r in cap.iterrows()]
    return {"scheme_rate": round(float(rates.loc["scheme", "claim_rate"]), 4),
            "other_rate": round(float(rates.loc["other", "claim_rate"]), 4),
            "excess_claims_inr": round(float(excess_scheme_claims(rates)), 2),
            "over_cap_inr": round(float(cap["over_cap_inr"].sum()), 2),
            "quarters_over": int((cap["over_cap_inr"] > 0).sum()), "quarters": quarters,
            "cap_share": policy.FREE_GOODS_CAP_SHARE.value, "cap_clause": policy.FREE_GOODS_CAP_SHARE.clause,
            "stock_norm_months": policy.STOCK_STATEMENT_MONTHS.value, "stock_norm_clause": policy.STOCK_STATEMENT_MONTHS.clause,
            "approval_clause": policy.SCHEME_APPROVAL_CLAUSE}


# --- Caching (QA 21 Nov 2026, D-04) ------------------------------------------------------
# Results depend only on the data extract (loaded once per process). Handed out as copies.
def overview(basis: str = "current") -> dict:
    return copy.deepcopy(_overview(_check(basis)))


def plan(cfa: str, basis: str = "current") -> dict:
    return copy.deepcopy(_plan(cfa, _check(basis)))


def topups(basis: str = "current") -> dict:
    return copy.deepcopy(_topups(_check(basis)))


def returns(basis: str = "current") -> dict:
    return copy.deepcopy(_returns(_check(basis)))


def shares() -> dict:
    return copy.deepcopy(_shares())


def restatement() -> list[dict]:
    return copy.deepcopy(_restatement())


def schemes() -> dict:
    """For the NSM and CFO: scheme products' claim rate, and free goods against the 3% cap."""
    return copy.deepcopy(_schemes())
