"""Watch views (plain pandas, no model), run in parallel, then one digest by owner.

Tabs pick which views run: expiry & dispatch watch, allocation view, or all six for the
weekly digest. Each view returns rows, a one-line summary and citations.
"""
from functools import lru_cache

import numpy as np
import pandas as pd

from agent import policy
from agent.state import SankalpState, WatchResult
from agent.tools import cite, group_lists, table

MAX_ROWS = 50  # rows sent to the page; citations still cover every row used
DAYS_PER_MONTH = 30.44


def _shelf_share(expiry: pd.Series, on: pd.Series | pd.Timestamp, shelf_months: pd.Series) -> pd.Series:
    """Remaining shelf life as a share: (expiry - date) / shelf life."""
    return (expiry - on).dt.days / (shelf_months * DAYS_PER_MONTH)


def _view(view: str, owner: str, file: str, df: pd.DataFrame, summary: str, citations=None) -> dict:
    """citations: pass them when the rows shown are aggregates of other rows."""
    out: WatchResult = {"view": view, "owner": owner, "summary": summary,
                        "rows": df.head(MAX_ROWS).astype(str).to_dict("records"),
                        "citations": citations if citations is not None else ([cite(file, df)] if len(df) else [])}
    return {"watch": {view: out}}


def _skus() -> pd.DataFrame:
    s = table("sku_master.csv")[["sku_code", "shelf_life_months", "pts_inr"]].copy()
    s[["shelf_life_months", "pts_inr"]] = s[["shelf_life_months", "pts_inr"]].astype(float)
    return s


def expiry_radar(state: SankalpState) -> dict:
    """Stock under 60% of shelf life at the latest snapshot. Target: Rs 1.18 cr at Kolkata."""
    stock = table("cnf_stock_snapshot.csv")
    stock = stock[stock["snapshot_date"] == stock["snapshot_date"].max()].merge(_skus(), on="sku_code")
    stock["shelf_share"] = _shelf_share(stock["expiry_date"], stock["snapshot_date"], stock["shelf_life_months"])
    stock["value_inr"] = stock["qty_on_hand_packs"].astype(float) * stock["pts_inr"]
    risk = stock[stock["shelf_share"] < policy.MIN_SHELF_LIFE_SHARE.value].sort_values("value_inr", ascending=False)
    by_cfa = risk.groupby("cnf_city")["value_inr"].sum().sort_values(ascending=False)
    summary = "; ".join(f"{city} Rs {v / 1e5:.1f} L" for city, v in by_cfa.items()) or "None below 60%"
    return _view("expiry_radar", "Supply Chain", "cnf_stock_snapshot.csv",
                 risk[["cnf_city", "sku_code", "batch_no", "expiry_date", "shelf_share", "value_inr", "src_line"]], summary)


@lru_cache(maxsize=1)
def fefo_lines() -> pd.DataFrame:
    """Invoice lines with an `inverted` flag: the CFA shipped this batch while an older batch of
    the same SKU was available, proven by the same CFA shipping that older batch within 90 days.
    Evidence log P3 (fefo.py): E01 Mar-26 71.8%, Apr-26 77.9%, FY27Q1 77.7%, FY27Q2 70.7%."""
    s = table("primary_sales.csv")
    s = s[s["batch_no"] != ""].copy()
    s["packs"] = s["invoiced_qty"].astype(float) + s["free_qty"].astype(float)
    s = s[s["packs"] > 0].merge(table("batch_master.csv")[["batch_no", "expiry_date"]], on="batch_no", how="left")
    s = s.sort_values("invoice_date").reset_index(drop=True)
    inverted = np.zeros(len(s), dtype=bool)
    ahead = np.timedelta64(int(policy.FEFO_LOOKAHEAD_DAYS.value), "D")
    for _, g in s.groupby(["cnf_code", "sku_code"]):
        dates, expiry, idx = g["invoice_date"].values, g["expiry_date"].values, g.index.values
        first = np.searchsorted(dates, dates, side="right")
        last = np.searchsorted(dates, dates + ahead, side="right")
        for i in range(len(g)):
            if first[i] < last[i] and (expiry[first[i]:last[i]] < expiry[i]).any():
                inverted[idx[i]] = True
    s["inverted"] = inverted
    s["inverted_packs"] = s["packs"] * s["inverted"]
    s["month"] = s["invoice_date"].dt.to_period("M")
    return s


def fefo_share(months: int = int(policy.FEFO_WINDOW_MONTHS.value)) -> pd.DataFrame:
    """Share of packs inverted per CFA, over a rolling window of `months` ending each month."""
    m = fefo_lines().groupby(["month", "cnf_code"])[["inverted_packs", "packs"]].sum().unstack("cnf_code").fillna(0)
    rolled = m.rolling(months, min_periods=months).sum()
    return (rolled["inverted_packs"] / rolled["packs"]).dropna(how="all")


def fefo_alert(state: SankalpState) -> dict:
    """Alert a CFA when over 35% of its packs over 3 months skip an older batch.
    Targets: Kolkata (CF-E01) alerts from March 2026; no other CFA ever does."""
    share = fefo_share()
    latest = share.iloc[-1]
    alerting = share.gt(policy.FEFO_ALERT_SHARE.value)
    since = {cfa: str(alerting.index[alerting[cfa]].min()) for cfa in alerting if alerting[cfa].any()}
    lines = fefo_lines()
    window = lines[lines["month"] > share.index[-1] - int(policy.FEFO_WINDOW_MONTHS.value)]
    rows = window[window["inverted"] & window["cnf_code"].isin(since)].sort_values("invoice_date", ascending=False)
    if since:
        summary = "; ".join(f"ALERT {cfa}: {latest[cfa]:.1%} of packs skip an older batch (alerting since {m})"
                            for cfa, m in since.items())
    else:
        summary = "No CFA above 35%"
    summary += ". Others: " + ", ".join(f"{c} {v:.0%}" for c, v in latest.items() if c not in since)
    return _view("fefo_alert", "Supply Chain", "primary_sales.csv",
                 rows[["invoice_no", "invoice_date", "cnf_code", "sku_code", "batch_no", "expiry_date", "packs", "src_line"]],
                 summary)


def short_dated(state: SankalpState) -> dict:
    """Invoice lines billed below 60% shelf life, all CFAs, last four quarters (~Rs 6.28 cr a year)."""
    sales = table("primary_sales.csv")
    start = pd.Timestamp(policy.SNAPSHOT_DATE) - pd.DateOffset(years=1)
    sales = sales[sales["invoice_date"] > start]
    batches = table("batch_master.csv")[["batch_no", "expiry_date"]]
    s = sales.merge(batches, on="batch_no").merge(_skus(), on="sku_code")
    s["shelf_share"] = _shelf_share(s["expiry_date"], s["invoice_date"], s["shelf_life_months"])
    short = s[s["shelf_share"] < policy.MIN_SHELF_LIFE_SHARE.value]
    by_cfa = short["net_value_inr"].astype(float).groupby(short["cnf_code"]).sum()
    summary = "; ".join(f"{c} Rs {v / 1e5:.1f} L" for c, v in by_cfa.sort_values(ascending=False).items())
    return _view("short_dated", "Supply Chain", "primary_sales.csv",
                 short[["invoice_no", "invoice_date", "cnf_code", "sku_code", "batch_no", "shelf_share", "src_line"]],
                 summary or "No short-dated billing")


def cover_table() -> pd.DataFrame:
    """Latest snapshot, one row per CFA and SKU, valued at PTS.
    Outward is per CFA and SKU, repeated on every batch row: take it once; sum stock over batches."""
    stock = table("cnf_stock_snapshot.csv")
    stock = stock[stock["snapshot_date"] == stock["snapshot_date"].max()].copy()
    stock[["qty_on_hand_packs", "avg_monthly_outward_packs"]] = stock[
        ["qty_on_hand_packs", "avg_monthly_outward_packs"]].astype(float)
    by = ["cnf_code", "cnf_city", "sku_code"]
    per_sku = stock.groupby(by).agg(
        stock_packs=("qty_on_hand_packs", "sum"), outward_packs=("avg_monthly_outward_packs", "first")).reset_index()
    per_sku["src_lines"] = group_lists(stock, by, "src_line")
    pts = _skus().set_index("sku_code")["pts_inr"]
    per_sku["stock_value"] = per_sku["stock_packs"] * per_sku["sku_code"].map(pts)
    per_sku["outward_value"] = per_sku["outward_packs"] * per_sku["sku_code"].map(pts)
    per_sku["cover_months"] = (per_sku["stock_value"] / per_sku["outward_value"].where(per_sku["outward_value"] > 0)).round(2)
    return per_sku


def cover_by_cfa(per_sku: pd.DataFrame) -> pd.Series:
    """Months of cover on VALUE: stock x PTS / monthly outward x PTS (evidence log, Sep-26 snapshot).
    Zero outward gives NaN, shown as 'n/a', never a division by zero."""
    g = per_sku.groupby(["cnf_code", "cnf_city"])[["stock_value", "outward_value"]].sum()
    return (g["stock_value"] / g["outward_value"].where(g["outward_value"] > 0)).round(2)


def national_cover(per_sku: pd.DataFrame) -> float:
    return round(per_sku["stock_value"].sum() / per_sku["outward_value"].sum(), 2)


def unfilled_orders(start, end) -> pd.DataFrame:
    """One row per invoice and SKU: unfilled value = (ordered - invoiced - free, floored at 0) x PTS.
    An order split over batches repeats ordered_qty on each batch row, so it is taken once.
    Evidence log: H1 FY27 Rs 18.30 cr (14.76 in scheme windows, 3.54 outside); L4Q Rs 33.31 cr."""
    s = _sales()
    s["ordered_qty"] = pd.to_numeric(s["ordered_qty"], errors="coerce")  # a few blanks: no unfilled claimed
    s = s[s["invoice_date"].between(pd.Timestamp(start), pd.Timestamp(end))]
    by = ["invoice_no", "sku_code"]
    g = s.groupby(by).agg(
        invoice_date=("invoice_date", "first"), cnf_code=("cnf_code", "first"), ordered=("ordered_qty", "first"),
        invoiced=("invoiced_qty", "sum"), free=("free_qty", "sum"), pts_inr=("pts_inr", "first")).reset_index()
    g["src_lines"] = group_lists(s, by, "src_line")
    g["unfilled_inr"] = (g["ordered"] - g["invoiced"] - g["free"]).clip(lower=0) * g["pts_inr"]
    d = g["invoice_date"]
    g["in_scheme_window"] = d.dt.month.isin(policy.SCHEME_WINDOW_MONTHS) & (d.dt.day >= policy.SCHEME_WINDOW_FROM_DAY.value)
    g["month"] = d.dt.to_period("M")
    return g


def donor_cover(unfilled: pd.DataFrame, keep_months: float = policy.DONOR_KEEP_MONTHS.value) -> pd.DataFrame:
    """Per product and month: unfilled value outside scheme windows, against what CFAs that are
    not short of that product held above `keep_months` of cover at the previous month-end
    (stock - keep x outward, x PTS, floored at 0), capped at the need.
    Final Plan: 49% of Rs 3.54 cr, doubled for a year, about Rs 3.5 cr."""
    need = unfilled[~unfilled["in_scheme_window"]].groupby(["month", "sku_code", "cnf_code"])["unfilled_inr"].sum()
    need = need[need > 0].reset_index()
    st = table("cnf_stock_snapshot.csv").copy()
    st[["qty_on_hand_packs", "avg_monthly_outward_packs"]] = st[["qty_on_hand_packs", "avg_monthly_outward_packs"]].astype(float)
    sp = st.groupby(["snapshot_date", "cnf_code", "sku_code"]).agg(
        stock=("qty_on_hand_packs", "sum"), outward=("avg_monthly_outward_packs", "first")).reset_index()
    sp["month"] = sp["snapshot_date"].dt.to_period("M") + 1  # month-end stock serves the next month
    sp["spare_inr"] = (sp["stock"] - keep_months * sp["outward"]).clip(lower=0) * sp["sku_code"].map(_skus().set_index("sku_code")["pts_inr"])
    short = need[["month", "sku_code", "cnf_code"]].assign(short=True)
    sp = sp.merge(short, on=["month", "sku_code", "cnf_code"], how="left")
    donors = sp[sp["short"].isna()].groupby(["month", "sku_code"])["spare_inr"].sum()
    out = pd.concat([need.groupby(["month", "sku_code"])["unfilled_inr"].sum().rename("need_inr"),
                     donors.rename("donor_spare_inr")], axis=1, join="outer").fillna(0)
    out = out[out["need_inr"] > 0]
    out["coverable_inr"] = out[["need_inr", "donor_spare_inr"]].min(axis=1)
    return out


def h1_window() -> tuple[pd.Timestamp, pd.Timestamp]:
    """The last six months of the extracts (H1 FY27: Apr-Sep 2026)."""
    end = pd.Timestamp(policy.SNAPSHOT_DATE)
    return (end.to_period("M") - 5).start_time, end


def allocation_gap(state: SankalpState) -> dict:
    """Months of cover per CFA (value basis), stock-outs, and stock held above 3 months.
    Targets: Kolkata 3.31, Lucknow 0.32, national 1.74; Lucknow 23 of 36 SKUs at zero;
    Kolkata Rs 1.66 cr above 3 months."""
    per_sku = cover_table()
    cover = cover_by_cfa(per_sku)
    zero = per_sku[per_sku["stock_packs"] == 0].groupby("cnf_city").size()
    per_sku["above_3m_value"] = (per_sku["stock_value"] - 3 * per_sku["outward_value"]).clip(lower=0)
    excess = per_sku.groupby("cnf_city")["above_3m_value"].sum()
    parts = [f"{city} {'n/a' if pd.isna(v) else v}" for (_, city), v in cover.sort_values().items()]
    summary = (f"Cover in months (value): {'; '.join(parts)}; national {national_cover(per_sku)}. "
               f"SKUs at zero: " + "; ".join(f"{c} {n}" for c, n in zero.sort_values(ascending=False).items()) +
               f". Above 3 months: " + "; ".join(f"{c} Rs {v / 1e7:.2f} cr" for c, v in excess.sort_values(ascending=False).head(2).items()))
    unfilled = unfilled_orders(*h1_window())
    cover_by_product = donor_cover(unfilled)
    outside = unfilled.loc[~unfilled["in_scheme_window"], "unfilled_inr"].sum()
    coverable = cover_by_product["coverable_inr"].sum()
    summary += (f". Last 6 months unfilled Rs {unfilled['unfilled_inr'].sum() / 1e7:.2f} cr, "
                f"Rs {outside / 1e7:.2f} cr outside scheme windows; other CFAs' stock above "
                f"{policy.DONOR_KEEP_MONTHS.value:g} months could have covered Rs {coverable / 1e7:.2f} cr "
                f"({coverable / outside:.0%}), about Rs {2 * coverable / 1e7:.1f} cr a year")
    rows = per_sku.assign(src_line=per_sku["src_lines"].map(lambda x: x[0])).drop(columns="src_lines")
    lines = [line for ls in per_sku["src_lines"] for line in ls]
    sales_lines = [line for ls in unfilled.loc[unfilled["unfilled_inr"] > 0, "src_lines"] for line in ls]
    view = _view("allocation_gap", "Demand Planning", "cnf_stock_snapshot.csv", rows.sort_values("cover_months"),
                 summary, citations=[cite("cnf_stock_snapshot.csv", pd.DataFrame({"src_line": lines})),
                                     cite("primary_sales.csv", pd.DataFrame({"src_line": sales_lines}))])
    return view


def _sales() -> pd.DataFrame:
    s = table("primary_sales.csv").copy()
    for col in ("invoiced_qty", "free_qty", "pts_inr", "net_value_inr"):
        s[col] = s[col].astype(float)
    return s


def scheme_skus() -> set[str]:
    """SKUs ever sold under a scheme code (15 in the extracts)."""
    s = table("primary_sales.csv")
    return set(s.loc[s["scheme_code"] != "", "sku_code"])


def scheme_claim_rates(start, end) -> pd.DataFrame:
    """Near-expiry + expired claim value / sales value, scheme vs other SKUs, by claim and
    invoice date in [start, end]. Evidence log P2: L4Q 4.25% (Rs 5.186 cr on Rs 122.05 cr) vs
    0.35% (Rs 0.276 cr on Rs 79.37 cr)."""
    s, c, skus = _sales(), table("expiry_claims.csv"), scheme_skus()
    s = s[s["invoice_date"].between(start, end)]
    c = c[c["claim_date"].between(start, end) & c["claim_type"].isin(["Near expiry", "Expired"])]
    out = pd.DataFrame({
        "sales_inr": [s.loc[s["sku_code"].isin(skus) == f, "net_value_inr"].sum() for f in (True, False)],
        "claims_inr": [c.loc[c["sku_code"].isin(skus) == f, "claim_value_inr"].astype(float).sum() for f in (True, False)],
    }, index=["scheme", "other"])
    out["claim_rate"] = out["claims_inr"] / out["sales_inr"]
    return out


def excess_scheme_claims(rates: pd.DataFrame) -> float:
    """Scheme sales x (scheme claim rate - other claim rate): Rs 4.76 cr over the L4Q."""
    return rates.loc["scheme", "sales_inr"] * (rates.loc["scheme", "claim_rate"] - rates.loc["other", "claim_rate"])


def free_goods_vs_cap() -> pd.DataFrame:
    """Free goods (free packs x line PTS) against 3% of all sales, per Indian FY quarter.
    Evidence log P2: over the cap FY25Q3-FY27Q1, Rs 3.954 cr; FY27Q2 at 2.82%."""
    s = _sales()
    s["free_goods_inr"] = s["free_qty"] * s["pts_inr"]
    s["quarter"] = s["invoice_date"].dt.to_period("Q-MAR")  # 2027Q1 = FY27 Q1 = Apr-Jun 2026
    q = s.groupby("quarter").agg(free_goods_inr=("free_goods_inr", "sum"), sales_inr=("net_value_inr", "sum"))
    q["share"] = q["free_goods_inr"] / q["sales_inr"]
    q["over_cap_inr"] = (q["free_goods_inr"] - policy.FREE_GOODS_CAP_SHARE.value * q["sales_inr"]).clip(lower=0)
    return q


def scheme_report(state: SankalpState) -> dict:
    """Scheme products' claim rate against other products, and free goods against the 3% cap.
    Informs the policy decision on scheme terms; it does not size what a change recovers."""
    start = pd.Timestamp(policy.SNAPSHOT_DATE) - pd.DateOffset(years=1) + pd.Timedelta(days=1)
    end = pd.Timestamp(policy.SNAPSHOT_DATE)
    rates = scheme_claim_rates(start, end)
    cap = free_goods_vs_cap()
    over = cap[cap["over_cap_inr"] > 0]
    latest = cap.iloc[-1]
    summary = (f"Last 4 quarters: scheme products claim {rates.loc['scheme', 'claim_rate']:.2%} of sales vs "
               f"{rates.loc['other', 'claim_rate']:.2%} for others; excess Rs {excess_scheme_claims(rates) / 1e7:.2f} cr. "
               f"Free goods over the 3% cap in {len(over)} quarters, Rs {over['over_cap_inr'].sum() / 1e7:.2f} cr; "
               f"latest quarter {latest['share']:.2%}.")
    s = table("primary_sales.csv")
    lines = s[s["invoice_date"].between(start, end) & s["sku_code"].isin(scheme_skus())]
    rows = cap.reset_index().assign(quarter=lambda d: d["quarter"].astype(str))
    return _view("scheme_report", "NSM and CFO", "primary_sales.csv", rows, summary,
                 citations=[cite("primary_sales.csv", lines)])


def claims_ageing(state: SankalpState) -> dict:
    """Pending claims and how long credits take against the 30-day rule.
    Targets: 360 pending worth Rs 95.9 L; credited claims take mean 45, median 42 days."""
    claims = table("expiry_claims.csv")
    pending = claims[claims["status"] == "Pending"].copy()
    pending["age_days"] = (pd.Timestamp(policy.SNAPSHOT_DATE) - pending["claim_date"]).dt.days
    value = pending["claim_value_inr"].astype(float).sum()
    credited = claims[claims["status"] == "Credited"]
    to_credit = (credited["credit_note_date"] - credited["claim_date"]).dt.days
    summary = (f"{len(pending)} pending, Rs {value / 1e5:.1f} L; credits take mean {to_credit.mean():.0f}, "
               f"median {to_credit.median():.0f} days against a 30-day rule")
    # TODO: plan's "69% over 30 days" - confirm which population and as-of date it uses.
    return _view("claims_ageing", "Commercial Finance", "expiry_claims.csv",
                 pending.sort_values("age_days", ascending=False)[
                     ["claim_no", "claim_date", "stockist_code", "claim_value_inr", "age_days", "src_line"]], summary)


VIEWS = {f.__name__: f for f in (expiry_radar, fefo_alert, short_dated, allocation_gap, scheme_report, claims_ageing)}
TAB_VIEWS = {
    "watch": ["expiry_radar", "fefo_alert", "short_dated"],
    "allocation": ["allocation_gap", "scheme_report"],
    "weekly": list(VIEWS),
}


def build_digest(state: SankalpState) -> dict:
    """One section per owner, so each person reads only what they act on."""
    digest: dict[str, list[str]] = {}
    for v in state.get("watch", {}).values():
        digest.setdefault(v["owner"], []).append(f"{v['view']}: {v['summary']}")
    cites = [c for v in state.get("watch", {}).values() for c in v["citations"]]
    return {"digest": digest, "citations": cites, "route": "clean"}
