"""Plan step 5: the allocation backtest replays Mar-Aug 2026 with data up to each month-end only."""
import pandas as pd
import pytest

from agent import allocation_backtest as ab
from agent import demand


def test_no_look_ahead():
    """Each plan at T uses normal months up to T only, and the snapshot at T."""
    for T in ab.STARTS:
        assert all(m <= pd.Timestamp(T).to_period("M") for m in demand.normal_months(T))


def test_actual_unfilled_matches_the_new_figure():
    """The 'actual' reference equals cuts on normal orders, counted once, Apr-Sep 2026 (Rs 4.01 cr)."""
    out = ab.run()
    assert round(out["actual_unfilled_inr"] / 1e7, 2) == round(demand.unfilled()["unmet_inr"].sum() / 1e7, 2) == 4.01


def test_findings():
    s = ab.run()["summary"]
    assert s["current"]["unfilled_inr"] < s["fy25"]["unfilled_inr"] < s["actual"]["unfilled_inr"] < s["old_report"]["unfilled_inr"]
    by = ab.run()["unfilled_by_cfa"]
    assert by["current"]["CF-N02"] < by["fy25"]["CF-N02"] / 1.5  # current shares roughly halve Lucknow's shortfall
    assert ab.run()["returns"]["short_after_return_inr"] == 0  # no return left a C&F short the next month


def test_deterministic():
    ab.run.cache_clear()
    a = ab.run()["summary"]
    ab.run.cache_clear()
    assert ab.run()["summary"] == a


def test_top_up_follows_the_cap():
    for T in ab.STARTS[:2]:
        p = demand.plan("current", T)
        assert (p["top_up"] <= (1.2 * p["allocated_month"]).round() + 1).all()
        assert ab.top_up("current", T).equals(p["top_up"])
