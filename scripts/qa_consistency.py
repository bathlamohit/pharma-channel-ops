"""QA: the screens agree with each other, every pending claim checks cleanly, and citations
point at rows that hold the numbers they back.

    python scripts/qa_consistency.py

Uses the API only (FastAPI TestClient), with all stores in a temporary folder.
"""
import os
import sys
import tempfile
from collections import Counter
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="sankalp-qa-"))
os.environ.update(CLAIMS_STORE=str(TMP / "claims.jsonl"), STOCK_ACTIONS=str(TMP / "actions.jsonl"),
                  AUDIT_LOG=str(TMP / "audit.jsonl"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app import app  # noqa: E402

c = TestClient(app)
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, bool(ok), detail))


def source(file: str, rows: list[int]) -> list[dict]:
    out, offset = [], 0
    while True:
        r = c.post("/api/source", json={"file": file, "rows": rows, "offset": offset}).json()
        out += r["rows"]
        offset += 50
        if offset >= r["total"]:
            return out


# 1. Expiry & dispatch: cards = plans = digest; every batch accounted for once ----------
so = c.get("/api/stock/overview").json()
plans = {card["cnf_code"]: c.get(f"/api/stock/plan?cfa={card['cnf_code']}").json() for card in so["cards"]}
for card in so["cards"]:
    p = plans[card["cnf_code"]]
    kinds = Counter(t["status"] for t in p["todo"])
    check(f"stock {card['cnf_code']} card counts = to-do", (kinds["short_dated"], kinds["at_risk"], kinds["block"]) ==
          (card["short_dated"], card["at_risk"], card["to_block"]), f"{dict(kinds)} vs card")
    todo_v = round(sum(t["value_inr"] for t in p["todo"]), 2)
    check(f"stock {card['cnf_code']} card value = to-do value", abs(todo_v - card["action_value_inr"]) < 1, f"{todo_v} vs {card['action_value_inr']}")
    all_b = [b for g in p["pick_list"] for b in g["batches"]]
    check(f"stock {card['cnf_code']} each batch once", len(all_b) == len({(b["sku_code"], b["batch_no"]) for b in all_b}) == card["batches"])
    check(f"stock {card['cnf_code']} stock value = sum of batches", abs(sum(b["value_inr"] for b in all_b) - card["stock_value_inr"]) < 1)
    check(f"stock {card['cnf_code']} one 'pick now' per product",
          all(sum(b["pick_now"] for b in g["batches"]) <= 1 for g in p["pick_list"]))
    for t in p["todo"]:
        if t["action"] == "cdc_return":
            check(f"stock {card['cnf_code']} return <= unsold", t["return_qty"] <= t["unsold_qty"] <= t["qty"], t["batch_no"])
    # citation rows hold the batch and its packs
    for t in p["todo"][:5]:
        rows = source("cnf_stock_snapshot.csv", t["src_lines"])
        ok = rows and all(r["batch_no"] == t["batch_no"] and r["cnf_code"] == card["cnf_code"] for r in rows)
        ok = ok and sum(int(r["qty_on_hand_packs"]) for r in rows) == t["qty"]
        check(f"stock {card['cnf_code']} citation rows = {t['batch_no']}", ok)

# 2. Allocation (plan step 2): cards = plans; top-ups and returns add up; both share bases --------
for basis in ("current", "fy25"):
    ao = c.get(f"/api/allocation/overview?basis={basis}").json()
    tu = c.get(f"/api/allocation/topups?basis={basis}").json()
    rt = c.get(f"/api/allocation/returns?basis={basis}").json()
    check(f"alloc[{basis}] top-up list = national", abs(tu["total_inr"] - ao["national"]["top_up_inr"]) < 5)
    check(f"alloc[{basis}] returns list = national", abs(rt["total_inr"] - ao["national"]["return_inr"]) < 1)
    unfilled, topup = 0, 0
    for card in ao["cards"]:
        p = c.get(f"/api/allocation/plan?cfa={card['cnf_code']}&basis={basis}").json()
        st = Counter(x["status"] for x in p["products"])
        check(f"alloc[{basis}] {card['cnf_code']} card counts = plan",
              (st["out of stock"], st["below target"], st["on target"], st["excess"]) ==
              (card["out_of_stock"], card["below_target"], card["on_target"], card["excess"]), f"{dict(st)}")
        check(f"alloc[{basis}] {card['cnf_code']} top-up = card", abs(sum(x["top_up_inr"] for x in p["products"]) - card["top_up_inr"]) < 1)
        check(f"alloc[{basis}] {card['cnf_code']} unfilled = card", abs(p["unfilled"]["total_inr"] - card["unfilled_6m_inr"]) < 1)
        unfilled += p["unfilled"]["total_inr"]
        topup += card["top_up_inr"]
        for x in p["products"]:
            cap = round(1.2 * x["allocated_month"]) + 1
            if x["top_up"] > cap or (x["status"] == "excess" and x["top_up"]) or (x["status"] != "excess" and x["return_qty"]):
                check(f"alloc[{basis}] {card['cnf_code']} {x['sku_code']} top-up/return rules", False, str(x))
    check(f"alloc[{basis}] unfilled per C&F adds to national", abs(unfilled - ao["national"]["unfilled_6m_inr"]) < 1)
    check(f"alloc[{basis}] top-up per C&F adds to national", abs(topup - ao["national"]["top_up_inr"]) < 5)
ao = c.get("/api/allocation/overview").json()
rs = {r["figure"]: r for r in c.get("/api/allocation/restatement").json()["rows"]}
check("restatement: old unfilled = new + scheme cuts", abs(rs["Orders not filled, last 6 months (Rs cr)"]["old"] -
      rs["Orders not filled, last 6 months (Rs cr)"]["new_current_shares"] - rs["Cuts on scheme orders, last 6 months (Rs cr)"]["new_current_shares"]) < 0.015)

# 3. Digest = screens -------------------------------------------------------------------
dg = c.get("/api/digest").json()
stats = {s["owner"]: {x["label"]: x["value"] for x in s["stats"]} for s in dg["sections"]}
check("digest out of stock = allocation", stats["Demand Planning"]["Out of stock"] == str(ao["national"]["out_of_stock"]))
check("digest months of stock = allocation", stats["Demand Planning"]["Months of stock, national"] == str(ao["national"]["cover_months"]))
check("digest consent batches = expiry", stats["Supply Chain"]["Bill with consent only"] == str(sum(x["short_dated"] for x in so["cards"])))
check("digest at-risk batches = expiry", stats["Supply Chain"]["Will not sell in time"] == str(sum(x["at_risk"] for x in so["cards"])))
first = [t for s in dg["sections"] if s["owner"] == "Supply Chain" for t in s["todo"]][:5]
earliest = sorted((t for p in plans.values() for t in p["todo"]), key=lambda t: (t["act_by"], -t["value_inr"]))[:5]
check("digest supply to-do = 5 earliest tasks", [e["batch_no"] in f["text"] for e, f in zip(earliest, first)] == [True] * 5)

# 4. Every pending register claim: checks run, money is right, citations hold -------------
claims = c.get("/api/claims?status=Pending&limit=1000").json()
routes, problems = Counter(), []
for i, cl in enumerate(claims):
    out = c.post("/api/claim/register", json={"claim_no": cl["claim_no"]})
    if out.status_code != 200:
        problems.append(f"{cl['claim_no']} HTTP {out.status_code}")
        continue
    body = out.json()
    routes[body["route"]] += 1
    ln = body["lines"][0]
    rec = ln["recommendation"]
    if body["usage"]:
        problems.append(f"{cl['claim_no']} called a model")
    if ln["route"] != "needs_person" and len(ln["checks"]) != 8:
        problems.append(f"{cl['claim_no']} ran {len(ln['checks'])} checks")
    if rec["action"] == "approve" and abs(rec["credit_inr"] - float(cl["claim_value_inr"] or 0)) > 1.01 and cl["claim_value_inr"]:
        problems.append(f"{cl['claim_no']} credit {rec['credit_inr']} vs claimed {cl['claim_value_inr']}")
    for k in ("credit_inr", "credit_if_approved_inr"):
        v = rec.get(k)
        if v is not None and (v < 0 or round(v, 2) != v):
            problems.append(f"{cl['claim_no']} {k}={v}")
    if rec["action"] == "approve_part" and not (0 < rec["qty"] < int(float(cl["qty_claimed"]))):
        problems.append(f"{cl['claim_no']} part qty {rec['qty']}")
    if i < 40:  # citations of the supply check hold this stockist and batch
        sup = ln["checks"].get("chk_supplied", {})
        for cit in sup.get("citations", []):
            rows = source(cit["file"], cit["rows"])
            if not all(r["stockist_code"] == cl["stockist_code"] and r["batch_no"] == cl["batch_no"] for r in rows):
                problems.append(f"{cl['claim_no']} supply citation rows do not match")
check(f"all {len(claims)} pending claims checked ({dict(routes)})", not problems, "; ".join(problems[:5]))

# --- report ------------------------------------------------------------------------------
fails = [r for r in results if not r[1]]
for name, ok, detail in results:
    if not ok or "pending claims" in name or name.startswith("digest") or "adds" in name:
        print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail if not ok else ''}")
print(f"\n{len(results) - len(fails)} passed, {len(fails)} failed ({len(results)} checks)")
sys.exit(1 if fails else 0)
