"""Unfilled orders and donor sizing reproduce the evidence log (v3) and the Final Plan.
Needs data/clean/. No key."""
import pandas as pd
import pytest

from agent import watch


@pytest.fixture(scope="module")
def h1():
    return watch.unfilled_orders(*watch.h1_window())


def _split(u):
    total = u["unfilled_inr"].sum() / 1e7
    inside = u.loc[u["in_scheme_window"], "unfilled_inr"].sum() / 1e7
    return round(total, 2), round(inside, 2), round(total - inside, 2)


def test_h1_window_is_april_to_september_2026():
    assert watch.h1_window() == (pd.Timestamp("2026-04-01"), pd.Timestamp("2026-09-30"))


def test_unfilled_h1_split_by_scheme_window(h1):
    assert _split(h1) == (18.30, 14.76, 3.54)


def test_unfilled_last_four_quarters():
    assert _split(watch.unfilled_orders("2025-10-01", "2026-09-30")) == (33.31, 28.16, 5.15)


def test_unfilled_h1_by_cfa(h1):
    by_cfa = (h1.groupby("cnf_code")["unfilled_inr"].sum() / 1e7).round(2).to_dict()
    assert by_cfa == {"CF-E01": 1.07, "CF-N01": 3.37, "CF-N02": 6.23, "CF-S01": 3.37, "CF-S02": 2.63, "CF-W01": 1.63}


def test_donors_above_two_months_cover_49_percent_about_3_5_cr_a_year(h1):
    coverable = watch.donor_cover(h1)["coverable_inr"].sum()
    outside = h1.loc[~h1["in_scheme_window"], "unfilled_inr"].sum()
    assert coverable / outside == pytest.approx(0.49, abs=0.005)
    assert 2 * coverable / 1e7 == pytest.approx(3.5, abs=0.05)


@pytest.mark.parametrize("keep,per_year", [(2.5, 2.8), (1.5, 4.8)])
def test_range_by_how_much_donors_keep(h1, keep, per_year):
    """Final Plan: Rs 2.8-4.8 cr a year by how much donors keep."""
    assert 2 * watch.donor_cover(h1, keep)["coverable_inr"].sum() / 1e7 == pytest.approx(per_year, abs=0.05)


def test_a_short_cfa_is_never_a_donor(h1):
    cover = watch.donor_cover(h1)
    assert (cover["coverable_inr"] <= cover["need_inr"] + 1e-6).all()
    assert (cover["coverable_inr"] <= cover["donor_spare_inr"] + 1e-6).all()
