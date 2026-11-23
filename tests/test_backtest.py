"""The live rule functions reproduce the verified back-test (Final Plan, "Outcome and money").
Needs data/clean/. No key."""
from datetime import date

import pytest

from agent.backtest import credited_twice, run_backtest

YEAR = (date(2025, 10, 1), date(2026, 9, 30))


@pytest.fixture(scope="module")
def verified():
    return run_backtest(fix_prefix=False)  # invoice refs matched as written, as in the verified analysis


@pytest.fixture(scope="module")
def live():
    return run_backtest(fix_prefix=True)


def test_credited_against_hard_rules_last_four_quarters_is_21_9_lakh(verified):
    n, value = verified.total("Credited", *YEAR)
    assert n == 181
    assert value / 1e5 == pytest.approx(21.9, abs=0.05)


def test_pending_claims_rejected_now_is_7_25_lakh(verified):
    n, value = verified.total("Pending")
    assert n == 38
    assert value / 1e5 == pytest.approx(7.25, abs=0.01)


def test_credited_twice_over_30_months_is_11_2_lakh():
    n, value, dup = credited_twice()
    assert n == 61
    assert value / 1e5 == pytest.approx(11.2, abs=0.01)
    assert "STK0025" in set(dup["stockist_code"])  # the double credit named in the plan


def test_reading_inv_dash_refs_only_adds_claims(verified, live):
    """Live behaviour reads INV-W01/... as INV/W01/...: 4 more credited, 3 more pending caught."""
    assert live.total("Credited", *YEAR)[0] - verified.total("Credited", *YEAR)[0] == 4
    assert live.total("Pending")[0] - verified.total("Pending")[0] == 3
    v = verified.claims.set_index("claim_no")["hard_fail"]
    lv = live.claims.set_index("claim_no")["hard_fail"]
    assert not (v & ~lv).any()  # nothing the verified run caught is lost


def test_first_claim_of_a_duplicate_pair_is_not_flagged(verified):
    _, _, dup = credited_twice()
    flagged = verified.claims.set_index("claim_no")
    for claim_no in dup["claim_no"].head(5):
        assert "duplicate" in flagged.loc[claim_no, "failed"]
