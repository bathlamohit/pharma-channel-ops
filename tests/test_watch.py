"""Batch-order alert and scheme report reproduce the evidence log (P2, P3). Needs data/clean/. No key."""
import pandas as pd
import pytest

from agent import watch


@pytest.fixture(scope="module")
def monthly():
    return watch.fefo_share(months=1)


@pytest.mark.parametrize("month,share", [("2026-01", 0.174), ("2026-02", 0.424), ("2026-03", 0.718),
                                         ("2026-04", 0.779), ("2026-06", 0.813)])
def test_kolkata_monthly_inversion(monthly, month, share):
    assert monthly.loc[pd.Period(month, "M"), "CF-E01"] == pytest.approx(share, abs=0.0005)


def test_kolkata_quarterly_inversion():
    q = watch.fefo_share(months=3)
    assert q.loc[pd.Period("2026-06", "M"), "CF-E01"] == pytest.approx(0.777, abs=0.0005)  # FY27Q1
    assert q.loc[pd.Period("2026-09", "M"), "CF-E01"] == pytest.approx(0.707, abs=0.0005)  # FY27Q2


def test_alert_fires_for_kolkata_from_march_2026_and_no_other_cfa():
    share = watch.fefo_share()
    alerting = share.gt(0.35)
    assert str(alerting.index[alerting["CF-E01"]].min()) == "2026-03"
    assert not alerting.drop(columns="CF-E01").any().any()


def test_single_months_would_false_alarm_at_quarter_end(monthly):
    """Why the window is 3 months: other CFAs pass 35% in scheme-loading months."""
    assert monthly.drop(columns="CF-E01").gt(0.35).any().any()


def test_scheme_claim_rates_last_four_quarters():
    rates = watch.scheme_claim_rates(pd.Timestamp("2025-10-01"), pd.Timestamp("2026-09-30"))
    assert len(watch.scheme_skus()) == 15
    assert rates.loc["scheme", "sales_inr"] / 1e7 == pytest.approx(122.05, abs=0.005)
    assert rates.loc["other", "sales_inr"] / 1e7 == pytest.approx(79.37, abs=0.005)
    assert rates.loc["scheme", "claim_rate"] == pytest.approx(0.0425, abs=0.00005)
    assert rates.loc["other", "claim_rate"] == pytest.approx(0.0035, abs=0.00005)
    assert watch.excess_scheme_claims(rates) / 1e7 == pytest.approx(4.76, abs=0.005)


def test_free_goods_over_cap_by_quarter():
    cap = watch.free_goods_vs_cap()
    over = (cap["over_cap_inr"] / 1e7).round(3)
    expected = {"2025Q3": 1.103, "2025Q4": 0.897, "2026Q1": 0.885, "2026Q2": 0.387,
                "2026Q3": 0.235, "2026Q4": 0.094, "2027Q1": 0.354}  # pandas Q-MAR: 2025Q3 = FY25 Q3
    for q, v in expected.items():
        assert over[pd.Period(q, "Q-MAR")] == pytest.approx(v, abs=0.001), q
    assert over.sum() == pytest.approx(3.954, abs=0.001)
    assert cap["share"].iloc[-1] == pytest.approx(0.0282, abs=0.00005)
