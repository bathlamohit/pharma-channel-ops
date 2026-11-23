"""Plan step 4: dispatches under 60% shelf life (CO-POL-014 7.1), every one flagged, where and why."""
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from agent import short_dated
from agent.tools import table
from app import app

client = TestClient(app)


def test_total_matches_the_verified_figure_and_the_old_view():
    s = short_dated.summary()
    assert s["lines"] == 1171 and round(s["value_inr"] / 1e7, 3) == 6.262
    assert s["under_60_days"] == 0
    assert sum(c["value_inr"] for c in s["cfas"]) == pytest.approx(s["value_inr"], abs=1)
    assert sum(c["lines"] for c in s["cfas"]) == s["lines"]


def test_flagged_set_matches_an_independent_calculation():
    """Row by row: invoice line in the last four quarters, batch expiry from the batch master, < 60% shelf life."""
    expiry = dict(zip(table("batch_master.csv")["batch_no"], table("batch_master.csv")["expiry_date"]))
    shelf = dict(zip(table("sku_master.csv")["sku_code"], table("sku_master.csv")["shelf_life_months"].astype(float)))
    want = set()
    for r in table("primary_sales.csv").itertuples():
        if not (pd.Timestamp("2025-10-01") <= r.invoice_date <= pd.Timestamp("2026-09-30")) or r.batch_no not in expiry:
            continue
        if (expiry[r.batch_no] - r.invoice_date).days / (shelf[r.sku_code] * 30.44) < 0.6:
            want.add(int(r.src_line))
    assert set(short_dated.lines()["src_line"].astype(int)) == want


def test_every_line_has_a_reason_that_holds():
    d = short_dated.lines()
    assert d["reasons"].map(len).min() >= 1
    for r in d.itertuples():
        assert ("arrived_old" in r.reasons) == bool(r.share_first_seen < 0.70)
        assert ("scheme" in r.reasons) == (r.scheme_code != "")
        assert ("out_of_order" in r.reasons) == (r.out_of_order_share > 0.35)
        assert ("too_much" in r.reasons) == bool(pd.notna(r.cover_before) and r.cover_before > 2)
        assert (r.reasons == ["none"]) == (not any([r.arrived_old, r.too_much, r.out_of_order, r.scheme]))


def test_where_and_why_findings():
    s = short_dated.summary()
    reasons = {r["reason"]: r for r in s["reasons"]}
    assert round(reasons["arrived_old"]["value_inr"] / 1e7, 2) == 4.69  # 75% arrived at the C&F already aged
    cfas = {c["cnf_code"]: c for c in s["cfas"]}
    assert cfas["CF-E01"]["main_reason"] == "Picked out of order"
    assert all(c["main_reason"] == "Arrived old from the CDC" for k, c in cfas.items() if k != "CF-E01")


def test_lines_api_pages_and_filters():
    a = client.get("/api/stock/short-dated/lines?cfa=CF-E01").json()
    b = client.get("/api/stock/short-dated/lines?cfa=CF-E01&offset=50").json()
    assert a["total"] == 248 and len(a["rows"]) == 50 and a["rows"][0]["src_line"] != b["rows"][0]["src_line"]
    f = client.get("/api/stock/short-dated/lines?cfa=CF-E01&reason=out_of_order").json()
    assert f["total"] < a["total"] and all("Picked out of order" in r["reasons"] for r in f["rows"])
    assert client.get("/api/stock/short-dated/lines?cfa=XX").status_code == 404
    assert client.get("/api/stock/short-dated/lines?cfa=CF-E01&reason=bad").status_code == 422


def test_consent_steps(tmp_path, monkeypatch):
    from agent import stock_log
    monkeypatch.setattr(stock_log, "PATH", tmp_path / "a.jsonl")
    r = client.get("/api/stock/short-dated/lines?cfa=CF-S01").json()["rows"][0]
    body = {"cnf_code": "CF-S01", "sku_code": r["sku_code"], "batch_no": r["batch_no"], "by": "QA", "note": f"Invoice {r['invoice_no']}"}
    assert client.post("/api/stock/action", json={**body, "step": "Stockist agreed"}).status_code == 200
    assert client.post("/api/stock/action", json={**body, "step": "Stockist agreed"}).status_code == 409
    assert client.post("/api/stock/action", json={**body, "step": "Stockist agreed", "note": "Invoice NOPE"}).status_code == 422
    assert client.get("/api/stock/short-dated").json()["consent"] == {"agreed": 1, "no_agreement": 0}
