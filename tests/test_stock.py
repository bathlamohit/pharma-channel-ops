"""Expiry and dispatch plan (ADR 0014): statuses follow CO-POL-014 7.1/7.2 and CF 6.3, Sch 2 2.5,
and the plan agrees with the verified expiry radar."""
import pandas as pd
from fastapi.testclient import TestClient

from agent import policy, stock
from agent.watch import expiry_radar
from app import app

client = TestClient(app)


def test_under_60_value_matches_the_verified_radar():
    """Kolkata holds Rs 1.18 cr under 60% of shelf life (verified analysis)."""
    cards = {c["cnf_code"]: c for c in stock.overview()["cards"]}
    assert round(cards["CF-E01"]["under_60_value_inr"] / 1e7, 2) == 1.18
    radar = expiry_radar({})["watch"]["expiry_radar"]["summary"]
    assert radar.startswith("Kolkata Rs 117.9 L")


def test_one_row_per_batch_and_every_batch_has_a_status():
    b = stock.batches()
    assert not b.duplicated(["cnf_code", "sku_code", "batch_no"]).any()
    assert set(b["status"]) <= set(stock.ORDER)


def test_status_rules_follow_the_policy():
    b = stock.batches()
    short = b[b["status"] == "short_dated"]
    assert (short["shelf_share"] < policy.MIN_SHELF_LIFE_SHARE.value).all()
    assert (b[b["status"] == "block"]["days_left"] < policy.BLOCK_DAYS.value).all()
    sellable = b[b["status"].isin(["pick_first", "in_line", "at_risk"])]
    assert (sellable["shelf_share"] >= policy.MIN_SHELF_LIFE_SHARE.value).all()
    assert (b[b["status"] == "at_risk"]["unsold_qty"] > 0).all()


def test_pick_now_is_the_oldest_sellable_batch():
    b = stock.batches()
    for _, g in b[b["status"].isin(["pick_first", "in_line", "at_risk"])].groupby(["cnf_code", "sku_code"]):
        assert g.sort_values("expiry_date").iloc[0]["pick_now"]
        assert g["pick_now"].sum() == 1


def test_cdc_returns_never_ask_for_more_than_others_can_take():
    for cfa in ("CF-E01", "CF-W01", "CF-S01"):
        for t in stock.plan(cfa)["todo"]:
            if t["action"] == "cdc_return":
                assert t["return_qty"] <= t["unsold_qty"]
                assert t["return_qty"] <= sum(k["can_take"] for k in t["takers"])
                assert all(k["cnf_code"] != cfa for k in t["takers"])


def test_plan_api_todo_is_sorted_by_act_by_and_cites_the_snapshot():
    p = client.get("/api/stock/plan?cfa=CF-E01").json()
    dates = [t["act_by"] for t in p["todo"]]
    assert dates == sorted(dates)
    assert p["fefo"]["alert"] and p["fefo"]["latest"] == 0.707
    assert p["citations"][0]["file"] == "cnf_stock_snapshot.csv"
    assert client.get("/api/stock/plan?cfa=CF-XX").status_code == 404


def test_actions_are_recorded_in_order():
    base = {"cnf_code": "CF-E01", "sku_code": "PFL1004", "batch_no": "A2600468", "by": "Asha Rao", "qty": 261}
    assert client.post("/api/stock/action", json={**base, "step": "Return approved"}).status_code == 409
    assert client.post("/api/stock/action", json={**base, "step": "Return requested"}).status_code == 200
    assert client.post("/api/stock/action", json={**base, "step": "Return approved"}).status_code == 200
    assert client.post("/api/stock/action", json={**base, "step": "Teleported"}).status_code == 409
    steps = [a["step"] for a in client.get("/api/stock/plan?cfa=CF-E01").json()["actions"]]
    assert steps == ["Return requested", "Return approved"]


# --- Not-moving watch list (plan step 3) ----------------------------------------------------
def test_not_moving_matches_an_independent_calculation():
    """Sellable batch, present at the previous snapshot, sold under 5% since: recomputed from raw snapshot rows."""
    from agent.tools import table
    st = table("cnf_stock_snapshot.csv")
    st = st[st["batch_no"] != ""]
    qty = lambda day: st[st["snapshot_date"] == pd.Timestamp(day)].groupby(["cnf_code", "sku_code", "batch_no"])[  # noqa: E731
        "qty_on_hand_packs"].apply(lambda x: x.astype(float).sum())
    now, before = qty("2026-09-30"), qty("2026-08-31")
    b = stock.batches()
    expect = set()
    for r in b[b["status"].isin(["pick_first", "in_line", "at_risk"])].itertuples():
        k = (r.cnf_code, r.sku_code, r.batch_no)
        if k in before.index and before[k] > 0 and (before[k] - now[k]) / before[k] < 0.05:
            expect.add(k)
    got = set(map(tuple, b.loc[b["not_moving"], ["cnf_code", "sku_code", "batch_no"]].values))
    assert got == expect and len(got) == 61


def test_watch_list_equals_the_cards_and_explains_each_case():
    o = {c["cnf_code"]: c for c in stock.overview()["cards"]}
    for cfa, card in o.items():
        p = stock.plan(cfa)
        assert len(p["watch"]) == card["not_moving"]
        for w in p["watch"]:
            assert w["not_moving"] and w["sold_share"] < 0.05 and w["status"] in ("pick_first", "in_line", "at_risk")
            assert w["title"] == ("Batch to pick first is not moving" if w["pick_now"] else "Waiting behind an older batch")
    assert stock.plan("CF-E01")["watch_since"] == "2026-08-31"


def test_checked_with_cfa_step(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from agent import stock_log
    from app import app
    monkeypatch.setattr(stock_log, "PATH", tmp_path / "a.jsonl")
    w = stock.plan("CF-E01")["watch"][0]
    c = TestClient(app)
    body = {"cnf_code": "CF-E01", "sku_code": w["sku_code"], "batch_no": w["batch_no"], "step": "Checked with CFA", "by": "QA"}
    assert c.post("/api/stock/action", json=body).status_code == 200
    assert c.post("/api/stock/action", json=body).status_code == 409
