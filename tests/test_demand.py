"""Plan step 1 (docs/allocation-demand-plan.md): demand from invoices.

Each figure is checked against an independent calculation written here with plain loops over
the cleaned sales rows, not through agent/demand.py, plus the client's rules (21-22 Nov 2026).
"""
from collections import defaultdict
from pathlib import Path

import pandas as pd
import pytest

from agent import demand, policy, stock
from agent.tools import table

ROOT = Path(__file__).resolve().parent.parent


def _rows():
    s = table("primary_sales.csv")
    return s.to_dict("records")


@pytest.fixture(scope="module")
def independent():
    """Normal month, unmet need (once) and FY25 dispatches, computed row by row."""
    rows = _rows()
    scheme_months = {r["invoice_date"].strftime("%Y-%m") for r in rows if r["scheme_code"] != ""}
    m, months = pd.Timestamp(policy.SNAPSHOT_DATE).to_period("M"), []
    while len(months) < 3:
        if m.strftime("%Y-%m") not in scheme_months:
            months.append(m.strftime("%Y-%m"))
        m -= 1
    # order lines: highest ordered once; dispatched summed
    lines = defaultdict(lambda: {"ordered": None, "disp": 0.0})
    for r in rows:
        k = (r["invoice_no"], r["sku_code"])
        o = pd.to_numeric(r["ordered_qty"], errors="coerce")
        L = lines[k]
        L.update(cfa=r["cnf_code"], stk=r["stockist_code"], date=r["invoice_date"], scheme=L.get("scheme", False) or r["scheme_code"] != "")
        if pd.notna(o) and (L["ordered"] is None or o > L["ordered"]):
            L["ordered"] = float(o)
        L["disp"] += float(r["invoiced_qty"] or 0) + float(r["free_qty"] or 0)
    normal, last_unmet, fy25 = defaultdict(float), {}, defaultdict(float)
    for (inv, sku), L in lines.items():
        mon = L["date"].strftime("%Y-%m")
        if "2024-04-01" <= L["date"].strftime("%Y-%m-%d") <= "2025-03-31":
            fy25[(L["cfa"], sku)] += L["disp"]
        if mon in months and not L["scheme"]:
            normal[(L["cfa"], sku)] += L["disp"] / 3
            key = (L["stk"], sku, mon)
            un = max(0.0, (L["ordered"] or 0) - L["disp"])
            if key not in last_unmet or (L["date"], inv) > last_unmet[key][0]:
                last_unmet[key] = ((L["date"], inv), L["cfa"], un)
    unmet = defaultdict(float)
    for (stk, sku, mon), (_, cfa, un) in last_unmet.items():
        unmet[(cfa, sku)] += un / 3
    return {"months": months, "normal": normal, "unmet": unmet, "fy25": fy25}


def test_report_field_is_not_used():
    """The client confirmed avg_monthly_outward_packs is unreliable: demand.py must not read it."""
    src = (ROOT / "agent" / "demand.py").read_text()
    assert "avg_monthly_outward_packs" not in src.replace("The SAP field avg_monthly_outward_packs is NOT used", "")


def test_normal_months_skip_every_scheme_month(independent):
    assert [str(m) for m in demand.normal_months()] == independent["months"] == ["2026-08", "2026-07", "2026-05"]
    assert [str(m) for m in demand.normal_months("2026-06-30")] == ["2026-05", "2026-04", "2026-02"]


def test_normal_month_and_unmet_match_independent_calculation(independent):
    d = demand.demand()
    for k in set(independent["normal"]) | set(independent["unmet"]):
        assert d.loc[k, "normal_month"] == pytest.approx(independent["normal"][k], abs=1e-6), k
        assert d.loc[k, "unmet_month"] == pytest.approx(independent["unmet"][k], abs=1e-6), k
    assert (d["real_need_month"] == d["normal_month"] + d["unmet_month"]).all()


def test_unmet_need_is_counted_once():
    """A cut line that is re-ordered must not add up twice: once per stockist, SKU and month."""
    lines = demand.order_lines()
    win = lines[lines["month"].isin(demand.normal_months()) & ~lines["is_scheme"]]
    every_cut = win.groupby(["cnf_code", "sku_code"])["unmet"].sum() / 3
    once = demand.demand()["unmet_month"]
    assert (once <= every_cut.reindex(once.index).fillna(0) + 1e-9).all()
    # In this extract no stockist has two cut lines for one SKU in one month (checked: 0 of 1,085
    # cut lines), so "once" and "every cut" agree here. The rule itself is proved below.
    assert once.sum() == pytest.approx(every_cut.sum())


def test_count_once_rule_on_a_reorder():
    """Synthetic: a stockist orders 100, gets 60 (40 cut), re-orders the 40 and gets 10 (30 cut).
    The real shortfall is 30, not 40 + 30 = 70: only the last order of the month counts."""
    lines = pd.DataFrame([
        {"cnf_code": "CF-N02", "sku_code": "PFL1201", "stockist_code": "STK0001", "invoice_no": "INV/A",
         "invoice_date": pd.Timestamp("2026-08-03"), "month": pd.Period("2026-08", "M"), "is_scheme": False, "unmet": 40.0},
        {"cnf_code": "CF-N02", "sku_code": "PFL1201", "stockist_code": "STK0001", "invoice_no": "INV/B",
         "invoice_date": pd.Timestamp("2026-08-17"), "month": pd.Period("2026-08", "M"), "is_scheme": False, "unmet": 30.0},
        {"cnf_code": "CF-N02", "sku_code": "PFL1201", "stockist_code": "STK0002", "invoice_no": "INV/C",
         "invoice_date": pd.Timestamp("2026-08-05"), "month": pd.Period("2026-08", "M"), "is_scheme": False, "unmet": 15.0},
        {"cnf_code": "CF-N02", "sku_code": "PFL1201", "stockist_code": "STK0002", "invoice_no": "INV/D",
         "invoice_date": pd.Timestamp("2026-08-26"), "month": pd.Period("2026-08", "M"), "is_scheme": True, "unmet": 99.0},
    ])
    assert demand._unmet_once(lines)[("CF-N02", "PFL1201")] == 30.0 + 15.0  # scheme line ignored


def test_fy25_shares_match_independent_and_sum_to_one(independent):
    sh = demand.fy25_shares()
    tot = defaultdict(float)
    for (cfa, sku), v in independent["fy25"].items():
        tot[sku] += v
    for (cfa, sku), v in independent["fy25"].items():
        assert sh[(cfa, sku)] == pytest.approx(v / tot[sku], abs=1e-9)
    assert sh.groupby(level="sku_code").sum().round(9).eq(1).all()
    cur = demand.current_shares()
    sums = cur.groupby(level="sku_code").sum()
    assert sums[sums > 0].round(9).eq(1).all()


@pytest.mark.parametrize("basis", ["current", "fy25"])
def test_top_up_follows_the_agreement(basis):
    """CF Sch 2 2.2: top up to 2 months of allocated volume; one shipment at most 1.2 months."""
    p = demand.plan(basis)
    a = p["allocated_month"]
    national = p["normal_month"].groupby(level="sku_code").transform("sum")
    assert (p["allocated_month"] - p["share"] * national).abs().max() < 1e-6
    assert (p["top_up"] <= (1.2 * a).round() + 1).all()
    assert (p["top_up"] >= 0).all()
    over = p["stock"] >= 2 * a
    assert (p.loc[over, "top_up"] == 0).all()
    exp = (2 * a - p["stock"]).clip(lower=0).clip(upper=1.2 * a).round()
    assert (p["top_up"] == exp).all()
    assert set(p["status"]) <= {"out of stock", "below target", "on target", "excess", "none"}
    assert (p.loc[p["status"] == "excess", "stock"] > 2 * p.loc[p["status"] == "excess", "allocated_month"]).all()


def test_returns_follow_the_client_rules():
    """Only batches keeping 60% shelf life and 60 days after 14 days in transit; >= Rs 5 lakh per SKU."""
    r = demand.returns("current")
    assert len(r) and (r["value_inr"] >= 500000).all()
    assert (r["return_qty"] <= r["spare"].round() + 1).all() and (r["return_qty"] <= r["eligible_qty"]).all()
    b = stock.batches()
    after = b["days_left"] - 14
    ok = b[(after / (b["shelf_life_months"] * 30.44) >= 0.6) & (after >= 60)].groupby(["cnf_code", "sku_code"])["qty"].sum()
    for k, row in r.iterrows():
        assert row["eligible_qty"] == ok[k]
    assert set(r.index.get_level_values("cnf_code")) == {"CF-E01"}


def test_share_gap_lucknow_and_kolkata():
    """The finding behind 'update shares now': on FY25 shares Lucknow is short and Kolkata over."""
    t = demand.share_table()
    assert t.loc["CF-N02", "gap_on_fy25_inr"] > 0 and t.loc["CF-E01", "gap_on_fy25_inr"] < 0
    assert t.loc["CF-N02", "share_change_pts"] > 5 and t.loc["CF-E01", "share_change_pts"] < -4
    assert t["fy25_share"].sum() == pytest.approx(1) and t["current_share"].sum() == pytest.approx(1)


def test_irregular_order_lines_and_the_highest_rule():
    irr = demand.irregular_order_lines()
    assert len(irr) == 45
    lines = demand.order_lines().set_index(["invoice_no", "sku_code"])
    for r in irr.itertuples():
        assert lines.loc[(r.invoice_no, r.sku_code), "ordered"] == r.taken == max(v for v in r.ordered_values if v == v)


def test_restatement_shows_old_new_and_reason():
    r = demand.restatement().set_index("figure")
    assert r.loc["Months of stock, Kolkata", "old"] == 3.31 and r.loc["Months of stock, Lucknow", "old"] == 0.32
    assert r.loc["Months of stock, national", "old"] == 1.74
    assert r.loc["Months of stock, national", "new_current_shares"] < 1
    assert r["reason"].str.len().gt(10).all()


def test_earlier_snapshot_uses_only_its_own_data():
    """as_of an earlier snapshot: normal months and stock come from that date, not later."""
    p = demand.plan("current", "2026-06-30")
    assert p["stock"].sum() > 0
    assert demand.demand("2026-06-30")["normal_month"].sum() != demand.demand()["normal_month"].sum()
