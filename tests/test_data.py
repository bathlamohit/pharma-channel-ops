"""Data-first tests: each reproduces a verified figure from the Final Plan.
Needs data/clean/ (python scripts/build_tables.py). No key."""
import pandas as pd
import pytest

from agent import tools


def test_cleaning_drops_known_duplicates():
    assert len(tools.table("expiry_claims.csv")) == 4526 - 23
    assert len(tools.table("primary_sales.csv")) == 93809 - 745


def test_q1_fy27_claims_value():
    c = tools.table("expiry_claims.csv")
    q1 = c[c["claim_date"].between("2026-04-01", "2026-06-30") & (c["status"] != "Rejected")]
    assert q1["claim_value_inr"].astype(float).sum() / 1e7 == pytest.approx(1.415, abs=0.002)


def test_pending_claims_count_and_value():
    p = tools.table("expiry_claims.csv").query("status == 'Pending'")
    assert len(p) == 360
    assert p["claim_value_inr"].astype(float).sum() / 1e5 == pytest.approx(95.9, abs=0.1)


def test_batch_lookup_cites_its_row_and_ignores_case():
    out = tools.get_batch("  k2300101 ")
    assert out["found"] and out["citation"]["file"] == "batch_master.csv" and out["citation"]["rows"] == [2]


def test_unknown_batch_is_reported_not_invented():
    assert tools.get_batch("ZZ999")["found"] is False


def test_cfa_codes_are_one_spelling():
    assert set(tools.table("cnf_stock_snapshot.csv")["cnf_code"]) == {
        "CF-E01", "CF-N01", "CF-N02", "CF-S01", "CF-S02", "CF-W01"}


def test_allocation_cover_on_value():
    """Evidence log, Sep-26 snapshot: E01 3.31, N02 0.32, national 1.74 (value basis)."""
    from agent.watch import cover_by_cfa, cover_table, national_cover
    per_sku = cover_table()
    cover = cover_by_cfa(per_sku).droplevel("cnf_city")
    assert cover["CF-E01"] == pytest.approx(3.31, abs=0.005)
    assert cover["CF-N02"] == pytest.approx(0.32, abs=0.005)
    assert national_cover(per_sku) == pytest.approx(1.74, abs=0.005)
    lucknow = per_sku[per_sku["cnf_code"] == "CF-N02"]
    assert (lucknow["stock_packs"] == 0).sum() == 23 and len(lucknow) == 36
    kolkata = per_sku[per_sku["cnf_code"] == "CF-E01"]
    above = (kolkata["stock_value"] - 3 * kolkata["outward_value"]).clip(lower=0).sum()
    assert above / 1e7 == pytest.approx(1.66, abs=0.005)


def test_zero_outward_shows_na_not_infinity():
    from agent.watch import cover_by_cfa
    df = pd.DataFrame({"cnf_code": ["X"], "cnf_city": ["Nowhere"], "stock_value": [100.0], "outward_value": [0.0]})
    assert cover_by_cfa(df).isna().all()


def test_fix_log_holds_only_real_changes():
    log = tools.table("fix_log.csv")
    real = log[log["fix"] != "exact duplicate dropped"]
    assert (real["before"] != real["after"]).all()
    assert not log["fix"].eq("expiry from batch master").any()  # the 270 blanks are stock-outs


def test_whole_numbers_are_written_as_integers():
    import csv
    with open(tools.CLEAN / "cnf_stock_snapshot.csv") as f:
        rows = list(csv.DictReader(f))
    assert not any(r["qty_on_hand_packs"].endswith(".0") for r in rows)
