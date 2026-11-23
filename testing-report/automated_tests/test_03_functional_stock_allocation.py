"""Expiry & dispatch, Allocation and the Weekly digest: workflows, recorded steps and consistency."""
import pytest

CFAS = ["CF-E01", "CF-N01", "CF-N02", "CF-S01", "CF-S02", "CF-W01"]


@pytest.mark.parametrize("cfa", CFAS)
def test_stock_plan_integrity(api, cfa):
    """TC-STK-1xx | Data integrity | CO-POL-014 7.1, 7.2; CF 6.3 | Per CFA: cards = to-do, each batch once, statuses follow the rules, one pick-now per product"""
    card = next(c for c in api.get("/api/stock/overview").json()["cards"] if c["cnf_code"] == cfa)
    p = api.get(f"/api/stock/plan?cfa={cfa}").json()
    batches = [b for g in p["pick_list"] for b in g["batches"]]
    assert len(batches) == card["batches"] == len({(b["sku_code"], b["batch_no"]) for b in batches})
    assert abs(sum(b["value_inr"] for b in batches) - card["stock_value_inr"]) < 1
    for b in batches:
        if b["status"] == "block":
            assert b["days_left"] < 60
        elif b["status"] == "short_dated":
            assert b["shelf_share"] < 0.6
        else:
            assert b["shelf_share"] >= 0.6 and b["days_left"] >= 60
    for g in p["pick_list"]:
        assert sum(b["pick_now"] for b in g["batches"]) <= 1
        sellable = [b for b in g["batches"] if b["status"] in ("pick_first", "in_line", "at_risk")]
        if sellable:
            assert min(sellable, key=lambda b: b["expiry_date"])["pick_now"]
    assert [t["act_by"] for t in p["todo"]] == sorted(t["act_by"] for t in p["todo"])


def test_cdc_return_workflow(api):
    """TC-STK-201 | End-to-end | CF Sch 2 2.5 | Batch return steps: request, approve, receive, in order; out-of-order and repeats refused; shown in the digest"""
    t = api.get("/api/stock/plan?cfa=CF-E01").json()["todo"][0]
    s = lambda step: api.post("/api/stock/action", json={"cnf_code": "CF-E01", "sku_code": t["sku_code"], "batch_no": t["batch_no"],  # noqa: E731
                                                          "qty": t["qty"], "step": step, "by": "QA RDM"})
    assert s("Return approved").status_code == 409
    assert s("Received at CDC").status_code == 409
    assert [s(x).status_code for x in ("Return requested", "Return approved", "Received at CDC")] == [200, 200, 200]
    assert s("Return requested").status_code == 409
    done = [a["step"] for a in api.get("/api/stock/plan?cfa=CF-E01").json()["actions"]]
    assert done == ["Return requested", "Return approved", "Received at CDC"]
    sc = next(x for x in api.get("/api/digest").json()["sections"] if x["owner"] == "Supply Chain")
    assert any(t["batch_no"] in d["text"] for d in sc["done"])


@pytest.mark.parametrize("basis", ["current", "fy25"])
@pytest.mark.parametrize("cfa", CFAS)
def test_allocation_plan_integrity(api, cfa, basis):
    """TC-ALC-1xx | Data integrity | CF Sch 2 2.2; plan step 2 | Per C&F and share basis: card = plan; statuses follow the 2-month target; top-up capped at 1.2 months; returns only for excess"""
    card = next(c for c in api.get(f"/api/allocation/overview?basis={basis}").json()["cards"] if c["cnf_code"] == cfa)
    p = api.get(f"/api/allocation/plan?cfa={cfa}&basis={basis}").json()
    st = {}
    for x in p["products"]:
        st[x["status"]] = st.get(x["status"], 0) + 1
        a = x["allocated_month"]
        if x["status"] == "out of stock":
            assert x["stock"] == 0 and a > 0
        if x["status"] in ("out of stock", "below target"):
            assert 1 <= x["top_up"] <= round(1.2 * a) + 1
        if x["status"] == "excess":
            assert x["top_up"] == 0 and (a == 0 or x["months_of_stock"] > 2)
        if x["return_qty"]:
            assert x["status"] == "excess" and x["return_inr"] >= 500000
    assert (st.get("out of stock", 0), st.get("below target", 0), st.get("on target", 0), st.get("excess", 0)) == \
        (card["out_of_stock"], card["below_target"], card["on_target"], card["excess"])


def test_allocation_topup_and_return_workflow(api):
    """TC-ALC-201 | End-to-end | CF Sch 2 2.2, 2.5 | Top-up steps per month and return steps in order; repeats refused; share change request national"""
    tu = api.get("/api/allocation/topups").json()["cfas"][0]["lines"][0]
    t = lambda step: api.post("/api/stock/action", json={"cnf_code": tu["cnf_code"], "sku_code": tu["sku_code"], "qty": tu["top_up"],  # noqa: E731
                                                          "step": step, "by": "QA Planner", "note": "Top-up for Oct 2026"})
    assert t("Dispatched from CDC").status_code == 409
    assert t("Allocation raised").status_code == 200 and t("Dispatched from CDC").status_code == 200
    assert t("Allocation raised").status_code == 409
    r = api.get("/api/allocation/returns").json()["returns"][0]
    ret = lambda step: api.post("/api/stock/action", json={"cnf_code": r["cnf_code"], "sku_code": r["sku_code"], "qty": r["return_qty"],  # noqa: E731
                                                            "step": step, "by": "QA RDM", "note": "Return to the CDC"})
    assert [ret(s).status_code for s in ("Return requested", "Return approved", "Received at CDC")] == [200, 200, 200]
    share = lambda step: api.post("/api/stock/action", json={"cnf_code": "NATIONAL", "step": step, "by": "QA Planner",  # noqa: E731
                                                              "note": "Move to current shares"})
    assert share("Share change approved").status_code == 409 and share("Share change requested").status_code == 200
    acts = api.get("/api/allocation/topups").json()["actions"]
    assert {(a["cnf_code"], a["step"]) for a in acts} >= {(tu["cnf_code"], "Allocation raised"), (r["cnf_code"], "Received at CDC")}
    dp = next(s for s in api.get("/api/digest").json()["sections"] if s["owner"] == "Demand Planning")
    assert any("Share change requested" in d["text"] for d in dp["done"])
    assert not any("approve the share change" in t["text"] for t in dp["todo"])  # the to-do goes once requested


def test_scheme_steps_are_national(api):
    """TC-ALC-202 | Functional | CO-POL-014 4.3 | Raise with NSM/CFO recorded once, national only"""
    ok = api.post("/api/stock/action", json={"cnf_code": "NATIONAL", "step": "Raised with NSM", "by": "QA Planner"})
    assert ok.status_code == 200
    assert api.post("/api/stock/action", json={"cnf_code": "NATIONAL", "step": "Raised with NSM", "by": "QA Planner"}).status_code == 409
    assert api.post("/api/stock/action", json={"cnf_code": "CF-E01", "step": "Raised with CFO", "by": "QA Planner"}).status_code == 422
    assert [a["step"] for a in api.get("/api/allocation/schemes").json()["actions"]] == ["Raised with NSM"]
    assert any(d["text"] == "Raised with NSM" for s in api.get("/api/digest").json()["sections"] if s["owner"] == "NSM and CFO" for d in s["done"])


def test_digest_matches_screens(api):
    """TC-DIG-101 | Consistency | ADR 0016 | Digest figures equal the screens; every to-do opens a screen; email text carries the same figures"""
    d = api.get("/api/digest").json()
    so, ao = api.get("/api/stock/overview").json(), api.get("/api/allocation/overview").json()
    st = {s["owner"]: {x["label"]: x["value"] for x in s["stats"]} for s in d["sections"]}
    assert st["Supply Chain"]["Bill with consent only"] == str(sum(c["short_dated"] for c in so["cards"]))
    assert st["Supply Chain"]["Will not sell in time"] == str(sum(c["at_risk"] for c in so["cards"]))
    assert st["Demand Planning"]["Out of stock"] == str(ao["national"]["out_of_stock"])
    assert st["Demand Planning"]["Months of stock, national"] == str(ao["national"]["cover_months"])
    for s in d["sections"]:
        assert s["todo"] and all(t["tab"] in ("claims", "watch", "allocation") and t["ref"] for t in s["todo"])
        for x in s["stats"]:
            assert f"{x['label']}: {x['value']}" in d["text"]


def test_source_viewer_rows_match_citation(api):
    """TC-SRC-101 | Data integrity | ADR 0004 | Cited snapshot rows hold the batch, CFA and packs the to-do states"""
    for t in api.get("/api/stock/plan?cfa=CF-W01").json()["todo"][:8]:
        rows = api.post("/api/source", json={"file": "cnf_stock_snapshot.csv", "rows": t["src_lines"]}).json()["rows"]
        assert rows and all(r["batch_no"] == t["batch_no"] and r["cnf_code"] == "CF-W01" for r in rows)
        assert sum(int(r["qty_on_hand_packs"]) for r in rows) == t["qty"]


def test_source_viewer_paging_and_fixes(api):
    """TC-SRC-102 | Functional | ADR 0004, 0005 | Source rows page 50 at a time, name dropped duplicates and show only real fixes"""
    rows = list(range(2, 200))
    a = api.post("/api/source", json={"file": "primary_sales.csv", "rows": rows}).json()
    b = api.post("/api/source", json={"file": "primary_sales.csv", "rows": rows, "offset": 50}).json()
    assert a["total"] == 198 and len(a["rows"]) + len(a["missing"]) == 50 and a["rows"][0] != b["rows"][0]
    assert all(f["before"] != f["after"] for fs in a["fixes"].values() for f in fs)
