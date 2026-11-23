"""Demand from invoices: the one place every screen will read demand from (plan step 1).

docs/allocation-demand-plan.md, section 4. The SAP field avg_monthly_outward_packs is NOT used:
the client confirmed it is unreliable (about 44-48% of real dispatches). Everything here comes
from primary_sales.csv, in SKU-master packs, per C&F and SKU. No model.

Definitions (client answers, 21-22 Nov 2026):
  order line       one invoice + SKU. Ordered = the HIGHEST ordered_qty on its rows, taken once
                   (split lines carry it on every row or on the first only; 45 lines neither).
  dispatched       invoiced + free packs (free goods included).
  scheme line      a line with a scheme code (not a date window).
  unmet need       ordered - invoiced - free, if above 0, on non-scheme lines. Re-orders: counted
                   once per stockist and SKU per month, from the last order of the month.
  normal month     average over the last 3 months with no scheme lines anywhere, of non-scheme
                   dispatches. This is the client's forecast stand-in.
  real need        normal month + unmet need over the same months.
  shares           FY25: share of dispatches in FY25 (client's instruction).
                   current: share of real need (our recommendation, agreed 22 Nov, awaiting the client).
  allocated volume national normal demand x share.
  top-up           min(2 x allocated - stock, 1.2 x allocated), 0 when over target (CF Sch 2 2.2).
  return           stock above 2 months of allocated volume, only from batches that still have 60%
                   shelf life and 60 days after 14 days in transit, and only if >= Rs 5 lakh per SKU.
"""
from functools import lru_cache

import pandas as pd

from agent import policy
from agent.tools import group_lists, stock_on_hand, table

KEYS = ["cnf_code", "sku_code"]


def _as_of(as_of=None) -> pd.Timestamp:
    return pd.Timestamp(as_of or policy.SNAPSHOT_DATE)


@lru_cache(maxsize=1)
def order_lines() -> pd.DataFrame:
    """One row per invoice and SKU (an order line)."""
    s = table("primary_sales.csv").copy()
    for c in ("ordered_qty", "invoiced_qty", "free_qty"):
        s[c] = pd.to_numeric(s[c], errors="coerce")
    s["is_scheme"] = s["scheme_code"] != ""
    s["src_line"] = s["src_line"].astype(int)
    by = ["invoice_no", "sku_code"]
    g = s.groupby(by, sort=False).agg(
        invoice_date=("invoice_date", "first"), cnf_code=("cnf_code", "first"),
        stockist_code=("stockist_code", "first"), ordered=("ordered_qty", "max"),
        invoiced=("invoiced_qty", "sum"), free=("free_qty", "sum"), is_scheme=("is_scheme", "any"),
        rows=("src_line", "size")).reset_index()
    g["src_lines"] = group_lists(s, by, "src_line", sort=False)
    g[["invoiced", "free"]] = g[["invoiced", "free"]].fillna(0)
    g["dispatched"] = g["invoiced"] + g["free"]
    g["unmet"] = (g["ordered"] - g["dispatched"]).clip(lower=0).fillna(0)
    g["month"] = g["invoice_date"].dt.to_period("M")
    return g


def irregular_order_lines() -> pd.DataFrame:
    """Split lines whose ordered_qty is neither on every row (same value) nor on the first row only.
    The client's rule: take the highest ordered_qty once. Listed in the client note."""
    s = table("primary_sales.csv").copy()
    s["o"] = pd.to_numeric(s["ordered_qty"], errors="coerce")
    s["line"] = s["src_line"].astype(int)
    s = s.sort_values("line")
    out = []
    for (inv, sku), g in s.groupby(["invoice_no", "sku_code"], sort=False):
        if len(g) < 2:
            continue
        filled = g["o"].notna()
        every_same = filled.all() and g["o"].nunique() == 1
        first_only = filled.iloc[0] and filled.sum() == 1
        if not (every_same or first_only):
            out.append({"invoice_no": inv, "sku_code": sku, "rows": len(g), "ordered_values": g["o"].tolist(),
                        "taken": float(g["o"].max()), "src_lines": g["line"].tolist()})
    return pd.DataFrame(out)


@lru_cache(maxsize=1)
def scheme_months() -> frozenset:
    lines = order_lines()
    return frozenset(lines.loc[lines["is_scheme"], "month"].unique())


def normal_months(as_of=None) -> list:
    """The last NORMAL_MONTHS months up to as_of with no scheme lines anywhere."""
    m = _as_of(as_of).to_period("M")
    out = []
    while len(out) < int(policy.NORMAL_MONTHS.value) and m >= order_lines()["month"].min():
        if m not in scheme_months():
            out.append(m)
        m -= 1
    return out


def _unmet_once(lines: pd.DataFrame) -> pd.DataFrame:
    """Unmet need counted once per stockist, SKU and month: the last order line of the month."""
    lines = lines[~lines["is_scheme"]].sort_values(["invoice_date", "invoice_no"])
    last = lines.groupby(["stockist_code", "sku_code", "month"]).tail(1)
    return last.groupby(KEYS)["unmet"].sum()


@lru_cache(maxsize=8)
def _demand(as_of: str) -> pd.DataFrame:
    months = normal_months(as_of)
    lines = order_lines()
    win = lines[lines["month"].isin(months)]
    n = len(months)
    normal = win[~win["is_scheme"]].groupby(KEYS)["dispatched"].sum() / n
    unmet = _unmet_once(win) / n
    end = _as_of(as_of).to_period("M")
    last3 = lines[lines["month"].between(end - 2, end)]
    dispatched = last3.groupby(KEYS)["dispatched"].sum() / 3
    df = pd.concat([dispatched.rename("dispatched_month"), normal.rename("normal_month"),
                    unmet.rename("unmet_month")], axis=1).fillna(0.0)
    df["real_need_month"] = df["normal_month"] + df["unmet_month"]
    return df


def demand(as_of=None) -> pd.DataFrame:
    """Per C&F and SKU: dispatched a month (last 3 months, all lines), normal month, unmet need a
    month and real need a month. Packs."""
    return _demand(str(_as_of(as_of).date())).copy()


@lru_cache(maxsize=1)
def fy25_shares() -> pd.Series:
    """Each C&F's share of FY25 dispatches, per SKU (sums to 1 per SKU)."""
    lines = order_lines()
    a, b = policy.SHARE_BASE
    d = lines[lines["invoice_date"].between(a, b)].groupby(KEYS)["dispatched"].sum()
    return (d / d.groupby(level="sku_code").transform("sum")).rename("fy25_share")


def current_shares(as_of=None) -> pd.Series:
    """Each C&F's share of real need now, per SKU (sums to 1 per SKU)."""
    need = demand(as_of)["real_need_month"]
    tot = need.groupby(level="sku_code").transform("sum")
    return (need / tot.where(tot > 0)).fillna(0.0).rename("current_share")


def _stock(as_of=None) -> pd.Series:
    return stock_on_hand(_as_of(as_of)).rename("stock")


def plan(basis: str = "current", as_of=None) -> pd.DataFrame:
    """Per C&F and SKU, on 'current' or 'fy25' shares: allocated volume, months of stock, top-up."""
    if basis not in ("current", "fy25"):
        raise ValueError("basis is 'current' or 'fy25'")
    d = demand(as_of)
    share = current_shares(as_of) if basis == "current" else fy25_shares()
    idx = d.index.union(share.index).union(_stock(as_of).index)
    df = d.reindex(idx).fillna(0.0)
    df["share"] = share.reindex(idx).fillna(0.0)
    national = df["normal_month"].groupby(level="sku_code").transform("sum")
    df["allocated_month"] = df["share"] * national
    df["stock"] = _stock(as_of).reindex(idx).fillna(0.0)
    pts = table("sku_master.csv").set_index("sku_code")["pts_inr"].astype(float)
    df["pts_inr"] = df.index.get_level_values("sku_code").map(pts)
    a = df["allocated_month"]
    df["months_of_stock"] = (df["stock"] / a.where(a > 0)).round(2)
    target, cap = policy.ALLOC_TARGET_MONTHS.value, policy.SHIPMENT_CAP_MONTHS.value
    df["top_up"] = (target * a - df["stock"]).clip(lower=0).clip(upper=cap * a).round()
    df["status"] = "on target"
    df.loc[df["stock"] < target * a - 0.5, "status"] = "below target"
    df.loc[(df["stock"] <= 0) & (a > 0), "status"] = "out of stock"
    df.loc[df["stock"] > target * a + 0.5, "status"] = "excess"
    df.loc[(a <= 0) & (df["stock"] > 0), "status"] = "excess"  # stock with no allocation
    df.loc[(a <= 0) & (df["stock"] <= 0), "status"] = "none"
    return df


def cfa_cover(basis: str = "current", as_of=None) -> pd.Series:
    """Months of stock per C&F on value: stock x PTS / allocated volume x PTS."""
    p = plan(basis, as_of)
    v = lambda c: (p[c] * p["pts_inr"]).groupby(level="cnf_code").sum()  # noqa: E731
    return (v("stock") / v("allocated_month")).round(2)


def returns(basis: str = "current", as_of=None) -> pd.DataFrame:
    """Stock above 2 months of allocated volume that may go back to the CDC: only batches with
    >= 60% shelf life and >= 60 days left after 14 days in transit; only if >= Rs 5 lakh per SKU."""
    from agent import stock
    p = plan(basis, as_of)
    b = stock.batches(None if as_of is None else str(_as_of(as_of).date()))
    t = policy.RETURN_TRANSIT_DAYS.value
    after = b["days_left"] - t
    ok = b[(after / (b["shelf_life_months"] * 30.44) >= policy.MIN_SHELF_LIFE_SHARE.value) &
           (after >= policy.BLOCK_DAYS.value)]
    eligible = ok.groupby(KEYS)["qty"].sum()
    spare = (p["stock"] - policy.ALLOC_TARGET_MONTHS.value * p["allocated_month"]).clip(lower=0)
    out = pd.concat([spare.rename("spare"), eligible.rename("eligible_qty")], axis=1).dropna()
    out["return_qty"] = out[["spare", "eligible_qty"]].min(axis=1).round()
    out["value_inr"] = (out["return_qty"] * out.index.get_level_values("sku_code").map(
        table("sku_master.csv").set_index("sku_code")["pts_inr"].astype(float))).round(2)
    return out[out["value_inr"] >= policy.RETURN_MIN_VALUE_INR.value].sort_values("value_inr", ascending=False)


def share_table(as_of=None) -> pd.DataFrame:
    """Per C&F (value at PTS): FY25 share, current share, allocated a month on each, real need a month."""
    rows = {}
    for basis in ("fy25", "current"):
        p = plan(basis, as_of)
        v = (p["allocated_month"] * p["pts_inr"]).groupby(level="cnf_code").sum()
        rows[f"{basis}_allocated_inr"] = v
        rows[f"{basis}_share"] = v / v.sum()
    p = plan("current", as_of)
    rows["real_need_inr"] = (p["real_need_month"] * p["pts_inr"]).groupby(level="cnf_code").sum()
    df = pd.DataFrame(rows)
    df["gap_on_fy25_inr"] = df["real_need_inr"] - df["fy25_allocated_inr"]
    df["share_change_pts"] = (df["current_share"] - df["fy25_share"]) * 100
    return df


def unfilled(as_of=None, months: int = 6) -> pd.DataFrame:
    """Orders cut for lack of stock over the last `months` months, per C&F and SKU, at PTS.
    Non-scheme lines: unmet need counted once per stockist, SKU and month (the real shortfall).
    Scheme lines: cut quantity reported separately (quarter-end loading, not lasting demand)."""
    end = _as_of(as_of).to_period("M")
    lines = order_lines()
    win = lines[lines["month"].between(end - (months - 1), end)]
    pts = table("sku_master.csv").set_index("sku_code")["pts_inr"].astype(float)
    normal = _unmet_once(win)
    scheme = win[win["is_scheme"]].groupby(KEYS)["unmet"].sum()
    orders = win[~win["is_scheme"] & (win["unmet"] > 0)].groupby(KEYS).size()
    df = pd.concat([normal.rename("unmet_packs"), scheme.rename("scheme_cut_packs"), orders.rename("cut_lines")],
                   axis=1).fillna(0.0)
    p = df.index.get_level_values("sku_code").map(pts)
    df["unmet_inr"] = (df["unmet_packs"] * p).round(2)
    df["scheme_cut_inr"] = (df["scheme_cut_packs"] * p).round(2)
    return df


def restatement(as_of=None) -> pd.DataFrame:
    """Old figure, new figure and reason, side by side (client asked for this, 22 Nov)."""
    from agent.watch import cover_by_cfa, cover_table, national_cover
    old_cover = cover_by_cfa(cover_table()).droplevel("cnf_city")
    city = dict(zip(table("cnf_stock_snapshot.csv")["cnf_code"], table("cnf_stock_snapshot.csv")["cnf_city"]))
    new_fy, new_cur = cfa_cover("fy25", as_of), cfa_cover("current", as_of)
    rows = []
    for cfa in old_cover.index:
        rows.append({"figure": f"Months of stock, {city.get(cfa, cfa)}", "old": float(old_cover[cfa]),
                     "new_fy25_shares": float(new_fy[cfa]), "new_current_shares": float(new_cur[cfa]),
                     "reason": "Old used the SAP report field (about half of real dispatches); new uses invoices"})
    p = plan("current", as_of)
    nat = (p["stock"] * p["pts_inr"]).sum() / (p["allocated_month"] * p["pts_inr"]).sum()
    rows.append({"figure": "Months of stock, national", "old": float(national_cover(cover_table())),
                 "new_fy25_shares": round(float(nat), 2), "new_current_shares": round(float(nat), 2),
                 "reason": "Same; shares do not change the national figure"})
    from agent.watch import donor_cover, h1_window, unfilled_orders
    old_u = unfilled_orders(*h1_window())
    old_out = old_u.loc[~old_u["in_scheme_window"], "unfilled_inr"].sum()
    old_cov = donor_cover(old_u)["coverable_inr"].sum()
    per = cover_table()
    old_k3 = (per["stock_value"] - 3 * per["outward_value"]).clip(lower=0)[per["cnf_code"] == "CF-E01"].sum()
    new_u = unfilled(as_of)
    rows += [
        {"figure": "Orders not filled, last 6 months (Rs cr)", "old": round(old_u["unfilled_inr"].sum() / 1e7, 2),
         "new_fy25_shares": round(new_u["unmet_inr"].sum() / 1e7, 2), "new_current_shares": round(new_u["unmet_inr"].sum() / 1e7, 2),
         "reason": "Old counted every cut line. New counts cuts on non-scheme lines once per stockist and month; "
                   "the rest of the old figure is cut scheme loading (next rows): new + scheme cuts = old"},
        {"figure": "Of which outside scheme weeks (Rs cr)", "old": round(old_out / 1e7, 2),
         "new_fy25_shares": round(new_u["unmet_inr"].sum() / 1e7, 2), "new_current_shares": round(new_u["unmet_inr"].sum() / 1e7, 2),
         "reason": "Scheme sales now identified by scheme code; all counted cuts are non-scheme"},
        {"figure": "Cuts on scheme orders, last 6 months (Rs cr)", "old": None,
         "new_fy25_shares": round(new_u["scheme_cut_inr"].sum() / 1e7, 2), "new_current_shares": round(new_u["scheme_cut_inr"].sum() / 1e7, 2),
         "reason": "Quarter-end loading the C&F could not fill; reported, not counted as demand"},
        {"figure": "Kolkata stock above 3 months (Rs cr)", "old": round(old_k3 / 1e7, 2), "new_fy25_shares": None, "new_current_shares": None,
         "reason": "Replaced by 'above 2 months of allocated volume' (client target, CF Sch 2 2.2); see returns"},
        {"figure": "Unfilled orders coverable from other C&Fs' spare", "old": round(float(old_cov / old_out), 3), "new_fy25_shares": None,
         "new_current_shares": None, "reason": "Retired: top-ups now come from the CDC (assumed able to supply); returns go to the CDC"},
    ]
    ret = returns("current", as_of)
    rows.append({"figure": "Returns to the CDC (Rs cr)", "old": None, "new_fy25_shares": round(returns("fy25", as_of)["value_inr"].sum() / 1e7, 2),
                 "new_current_shares": round(ret["value_inr"].sum() / 1e7, 2),
                 "reason": "Spare above 2 months; batches keep 60% after 14 days; at least Rs 5 L per SKU"})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    pd.set_option("display.width", 200)
    print("Normal months:", [str(m) for m in normal_months()])
    print(share_table().round({"fy25_share": 3, "current_share": 3, "share_change_pts": 1}).to_string())
    print(restatement().to_string())
    print(f"Irregular order lines: {len(irregular_order_lines())}")
