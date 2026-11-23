"""Allocation screen on demand from invoices (plan step 2; docs/allocation-demand-plan.md)."""
import pytest
from fastapi.testclient import TestClient

from agent import allocation, demand, policy
from app import app

client = TestClient(app)


@pytest.mark.parametrize("basis", ["current", "fy25"])
def test_overview_agrees_with_the_demand_module(basis):
    o = allocation.overview(basis)
    cover = demand.cfa_cover(basis)
    for c in o["cards"]:
        assert c["cover_months"] == pytest.approx(cover[c["cnf_code"]], abs=0.006)
    p = demand.plan(basis)
    assert o["national"]["top_up_inr"] == pytest.approx((p["top_up"] * p["pts_inr"]).sum(), abs=5)
    assert o["national"]["return_inr"] == pytest.approx(demand.returns(basis)["value_inr"].sum(), abs=1)
    assert o["national"]["cover_months"] == 0.85  # 30 Sep 2026: about 0.85 months against a 2-month target


def test_cards_equal_their_plans():
    o = allocation.overview()
    for c in o["cards"]:
        rows = allocation.plan(c["cnf_code"])["products"]
        st = {s: sum(r["status"] == s for r in rows) for s in ("out of stock", "below target", "on target", "excess")}
        assert (st["out of stock"], st["below target"], st["on target"], st["excess"]) == (c["out_of_stock"], c["below_target"], c["on_target"], c["excess"])
        assert sum(r["top_up_inr"] for r in rows) == pytest.approx(c["top_up_inr"], abs=1)


def test_advice_follows_the_status():
    for r in allocation.plan("CF-N02")["products"] + allocation.plan("CF-E01")["products"]:
        if r["status"] in ("out of stock", "below target"):
            assert r["action"] == "top_up" and r["top_up"] > 0 and "assumes the cdc can supply" in r["do"].lower()
            assert r["top_up"] <= round(policy.SHIPMENT_CAP_MONTHS.value * r["allocated_month"]) + 1
        elif r["status"] == "excess":
            assert r["action"] == "excess" and r["top_up"] == 0
            assert ("Return" in r["do"]) == (r["return_qty"] > 0)
        else:
            assert r["action"] == "none"


def test_topups_and_returns_lists_add_up():
    o, t, r = allocation.overview(), allocation.topups(), allocation.returns()
    assert t["total_inr"] == pytest.approx(o["national"]["top_up_inr"], abs=5)
    assert sum(len(c["lines"]) for c in t["cfas"]) == t["lines"] == o["national"]["top_up_lines"]
    assert r["total_inr"] == pytest.approx(o["national"]["return_inr"], abs=1)
    for x in r["returns"]:
        assert x["value_inr"] >= policy.RETURN_MIN_VALUE_INR.value
        assert x["batches"] and all(b["shelf_after_transit"] >= 0.6 for b in x["batches"])
        assert x["return_qty"] <= sum(b["qty"] for b in x["batches"])


def test_shares_view_marks_the_lucknow_gap():
    s = allocation.shares()
    lk = next(c for c in s["cfas"] if c["cnf_code"] == "CF-N02")
    kol = next(c for c in s["cfas"] if c["cnf_code"] == "CF-E01")
    assert lk["gap_on_fy25_inr"] > 0 and lk["over_step_limit"] and kol["gap_on_fy25_inr"] < 0
    assert sum(c["fy25_share"] for c in s["cfas"]) == pytest.approx(1, abs=1e-3)


def test_restatement_keeps_the_verified_old_figures():
    """The old figures stay pinned here, beside the new ones (client asked for side by side)."""
    rows = {r["figure"]: r for r in allocation.restatement()}
    assert rows["Months of stock, Kolkata"]["old"] == 3.31 and rows["Months of stock, Lucknow"]["old"] == 0.32
    assert rows["Months of stock, national"]["old"] == 1.74
    assert rows["Orders not filled, last 6 months (Rs cr)"]["old"] == 18.30
    assert rows["Of which outside scheme weeks (Rs cr)"]["old"] == 3.54
    assert rows["Kolkata stock above 3 months (Rs cr)"]["old"] == 1.66
    assert rows["Unfilled orders coverable from other C&Fs' spare"]["old"] == 0.491
    new = rows["Orders not filled, last 6 months (Rs cr)"]["new_current_shares"]
    scheme = rows["Cuts on scheme orders, last 6 months (Rs cr)"]["new_current_shares"]
    assert new + scheme == pytest.approx(18.30, abs=0.01)  # the old figure = real shortfall + cut scheme loading


def test_api_basis_and_steps():
    assert client.get("/api/allocation/overview?basis=fy25").json()["basis"] == "fy25"
    assert client.get("/api/allocation/overview?basis=fy99").status_code == 422
    assert client.get("/api/allocation/plan?cfa=CF-N02").json()["products"][0]["status"] == "out of stock"
    assert client.get("/api/allocation/plan?cfa=XX").status_code == 404
    for url in ("/api/allocation/topups", "/api/allocation/returns", "/api/allocation/shares", "/api/allocation/restatement"):
        assert client.get(url).status_code == 200
    ret = client.get("/api/allocation/returns").json()["returns"][0]
    step = {"cnf_code": ret["cnf_code"], "sku_code": ret["sku_code"], "by": "Asha Rao", "note": "Return to the CDC"}
    assert client.post("/api/stock/action", json={**step, "step": "Return approved"}).status_code == 409
    assert client.post("/api/stock/action", json={**step, "step": "Return requested"}).status_code == 200
    share = {"cnf_code": "NATIONAL", "by": "Asha Rao", "note": "Move to current shares"}
    assert client.post("/api/stock/action", json={**share, "step": "Share change approved"}).status_code == 409
    assert client.post("/api/stock/action", json={**share, "step": "Share change requested"}).status_code == 200
    assert [a["step"] for a in client.get("/api/allocation/shares").json()["actions"]] == ["Share change requested"]


def test_schemes_unchanged():
    s = allocation.schemes()
    assert (round(s["scheme_rate"] * 100, 2), round(s["other_rate"] * 100, 2)) == (4.25, 0.35)
    assert round(s["over_cap_inr"] / 1e7, 3) == 3.954
