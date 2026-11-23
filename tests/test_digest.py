"""Weekly digest (ADR 0016): built from the same plans as the work screens, one section per owner,
each to-do points at a screen, and steps recorded elsewhere appear under Done."""
from fastapi.testclient import TestClient

from agent import digest
from app import app

client = TestClient(app)


def section(d, owner):
    return next(s for s in d["sections"] if s["owner"] == owner)


def test_sections_carry_the_verified_figures():
    d = digest.build()
    assert [s["owner"] for s in d["sections"]] == ["Commercial Finance", "Supply Chain", "Demand Planning", "NSM and CFO"]
    claims = {x["label"]: x for x in section(d, "Commercial Finance")["stats"]}
    assert claims["Pending claims"]["value"] == "360" and claims["Pending claims"]["sub"] == "Rs 95.9 L"
    assert claims["Days to credit note"]["value"] == "45"
    alloc = {x["label"]: x for x in section(d, "Demand Planning")["stats"]}
    # plan step 2: demand from invoices (old 1.74 months / Rs 18.30 cr kept in the restatement)
    assert alloc["Months of stock, national"]["value"] == "0.85"
    assert alloc["Orders not filled, 6 months"]["value"] == "Rs 4.01 cr"
    assert alloc["Top-up from the CDC this month"]["value"] == "Rs 13.52 cr"
    schemes = {x["label"]: x for x in section(d, "NSM and CFO")["stats"]}
    assert schemes["Claims on scheme products"]["value"] == "4.25%"
    assert "Kolkata" in {x["label"]: x for x in section(d, "Supply Chain")["stats"]}["Batch-order alert"]["value"]


def test_every_todo_opens_a_screen():
    for s in digest.build()["sections"]:
        assert s["todo"], s["owner"]
        for t in s["todo"]:
            assert t["tab"] in {"claims", "watch", "allocation"} and t["ref"]


def test_steps_recorded_on_the_work_screens_show_as_done():
    client.post("/api/stock/action", json={"cnf_code": "CF-E01", "sku_code": "PFL1004", "batch_no": "A2600468",
                                           "step": "Return requested", "by": "Asha Rao"})
    client.post("/api/stock/action", json={"cnf_code": "CF-N02", "sku_code": "PFL1201", "step": "Allocation raised",
                                           "by": "Ravi K"})
    client.post("/api/stock/action", json={"cnf_code": "NATIONAL", "step": "Raised with CFO", "by": "Neha B"})
    d = client.get("/api/digest").json()
    assert [x["by"] for x in section(d, "Supply Chain")["done"]] == ["Asha Rao"]
    assert [x["by"] for x in section(d, "Demand Planning")["done"]] == ["Ravi K"]
    assert [x["text"] for x in section(d, "NSM and CFO")["done"]] == ["Raised with CFO"]


def test_email_text_has_the_same_figures():
    d = digest.build()
    for s in d["sections"]:
        assert s["title"].upper() in d["text"]
        for x in s["stats"]:
            assert f"{x['label']}: {x['value']}" in d["text"]


def test_demand_section_carries_restatement_notice():
    d = digest.build()
    sec = next(s for s in d["sections"] if s["owner"] == "Demand Planning")
    n = sec["notice"]
    assert n["tab"] == "allocation" and n["ref"] == "changes"
    assert "1.74 → 0.85" in n["text"] and "Rs 18.30 cr → Rs 4.01 cr" in n["text"]
    assert "Note: Figures restated" in d["text"]
