"""Backtesting and historical validation.

1. Headline figures recomputed independently from data/raw (scripts/qa_check.py) = app = verified.
2. Claim rules back-tested over the register (agent/backtest.py): verified figures, reproducible.
3. Chronological backtest of the stock forecast (agent/stock.py): forecast from snapshot T using only
   data at T, compare with later snapshots, against two naive baselines. No future data is used.
4. Money and date precision.
"""
import json
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import pandas as pd
import pytest

from conftest import EVIDENCE, ROOT

sys.path.insert(0, str(ROOT / "scripts"))
OUT = EVIDENCE / "backtest.json"


def save(key, value):
    data = json.loads(OUT.read_text()) if OUT.exists() else {}
    data[key] = value
    OUT.write_text(json.dumps(data, indent=1, default=str))


def test_independent_figures_match_app_and_verified():
    """TC-BKT-001 | Backtest | ADR 0008, 0009 | 30 headline figures: independent recomputation from raw = app = verified analysis"""
    import qa_check
    ind, app_ = qa_check.figures(), qa_check.served()
    rows, fails = [], []
    for k in sorted(set(ind) | set(app_) | set(qa_check.VERIFIED)):
        i, a, v = ind.get(k), app_.get(k), qa_check.VERIFIED.get(k)
        tol = qa_check.TOL.get(k, 0.006)
        ok = (i is None or a is None or qa_check.close(i, a, tol)) and (v is None or qa_check.close(i if i is not None else a, v, tol))
        if k == "claims.pending_list_len":
            ok = a == ind["claims.pending_count"]
        rows.append({"figure": k, "independent": i, "app": a, "verified": v, "tolerance": tol, "result": "PASS" if ok else "FAIL"})
        if not ok:
            fails.append(k)
    save("figures", rows)
    assert not fails, fails


def test_claim_rule_backtest_reproduces_and_is_deterministic():
    """TC-BKT-002 | Backtest | ADR 0003, 0008 | Rules over the register: Rs 21.9 L / 181 credited, Rs 7.25 L / 38 pending, 61 double credits; same result twice"""
    from datetime import date

    from agent.backtest import credited_twice, run_backtest
    year = (date(2025, 10, 1), date(2026, 9, 30))
    a, b = run_backtest(fix_prefix=False), run_backtest(fix_prefix=False)
    assert a.claims.equals(b.claims)  # deterministic
    cn, cv = a.total("Credited", *year)
    pn, pv = a.total("Pending")
    tn, tv, _ = credited_twice()
    assert (cn, round(cv / 1e5, 2)) == (181, 21.89)
    assert (pn, round(pv / 1e5, 2)) == (38, 7.25)
    assert (tn, round(tv / 1e5, 2)) == (61, 11.20)
    live = run_backtest(fix_prefix=True)
    ln, lv = live.total("Credited", *year)
    lpn, lpv = live.total("Pending")
    save("claim_rules", {"as_written": {"credited_l4q": [cn, round(cv, 2)], "pending": [pn, round(pv, 2)]},
                         "invoice_refs_normalised": {"credited_l4q": [ln, round(lv, 2)], "pending": [lpn, round(lpv, 2)]},
                         "credited_twice_30m": [tn, round(tv, 2)]})


ORIGINS = ["2026-03-31", "2026-04-30", "2026-05-31", "2026-06-30"]


def _snapshot_qty(day: str) -> pd.Series:
    from agent.tools import table
    s = table("cnf_stock_snapshot.csv")
    s = s[(s["snapshot_date"] == pd.Timestamp(day)) & (s["batch_no"] != "")].copy()
    s["qty"] = s["qty_on_hand_packs"].astype(float)
    return s.groupby(["cnf_code", "sku_code", "batch_no"])["qty"].sum()


def _forecast(b: pd.DataFrame, months: float) -> pd.Series:
    """The app's projection: each CFA sells its monthly outward, oldest sellable batch first.
    Short-dated and blocked batches take no orders (they need consent or are blocked)."""
    rem = {}
    for _, g in b.sort_values(["cnf_code", "sku_code", "expiry_date"]).groupby(["cnf_code", "sku_code"]):
        demand = g["outward"].iloc[0] * months
        for r in g.itertuples():
            key = (r.cnf_code, r.sku_code, r.batch_no)
            if r.status in ("block", "short_dated"):
                rem[key] = r.qty
                continue
            sold = min(r.qty, max(0.0, demand))
            demand -= sold
            rem[key] = r.qty - sold
    return pd.Series(rem)


@pytest.mark.parametrize("source", ["invoices", "report"])
def test_chronological_stock_forecast_backtest(source):
    """TC-BKT-003 | Backtest (chronological) | ADR 0014; plan step 3 | Forecast batch stock at T+h from snapshot T only, on normal demand (new) and the SAP field (old); compare with actual snapshots and naive baselines"""
    from agent import stock
    snaps = ["2026-03-31", "2026-04-30", "2026-05-31", "2026-06-30", "2026-07-31", "2026-08-31", "2026-09-30"]
    results = []
    for t in ORIGINS:
        b = stock.batches(t, source)  # uses only the snapshot at T and invoices up to T (no later data)
        assert b["as_of"].iloc[0] == pd.Timestamp(t)
        for h in (1, 2, 3):
            target = snaps[snaps.index(t) + h]
            actual = _snapshot_qty(target)
            idx = pd.MultiIndex.from_frame(b[["cnf_code", "sku_code", "batch_no"]])
            act = actual.reindex(idx).fillna(0.0).values
            start = b["qty"].values
            months = (pd.Timestamp(target) - pd.Timestamp(t)).days / 30.44
            model = _forecast(b, months).reindex(idx).values
            total_out = b.groupby(["cnf_code", "sku_code"])["outward"].first()
            share = b["qty"] / b.groupby(["cnf_code", "sku_code"])["qty"].transform("sum")
            prop = (b["qty"] - (share * b.set_index(["cnf_code", "sku_code"]).index.map(total_out).values * months)).clip(lower=0).values
            err = lambda f: float(abs(f - act).sum() / act.sum())  # noqa: E731  WAPE
            results.append({"source": source, "origin": t, "target": target, "horizon_months": h, "batches": int(len(b)),
                            "wape_model": round(err(model), 4), "wape_no_sales": round(err(start), 4),
                            "wape_proportional": round(err(prop), 4), "bias_model": round(float((model - act).sum() / act.sum()), 4)})
    data = json.loads(OUT.read_text()) if OUT.exists() else {}
    data.setdefault("stock_forecast", {})[source] = results
    OUT.write_text(json.dumps(data, indent=1, default=str))
    wins = sum(r["wape_model"] < r["wape_no_sales"] for r in results)
    assert wins >= len(results) - 1, "the forecast should beat 'nothing sells' almost everywhere"


def test_at_risk_flag_precision_recall():
    """TC-BKT-004 | Backtest (chronological) | ADR 0014; plan step 3 | 'Will not sell in time' flags at T, new (normal demand) vs old (SAP field): still in stock at the 60% date?"""
    from agent import stock
    snaps = pd.to_datetime(["2026-03-31", "2026-04-30", "2026-05-31", "2026-06-30", "2026-07-31", "2026-08-31", "2026-09-30"])
    summary = {}
    for source in ("invoices", "report"):
        out, tot = [], [0, 0, 0, 0]
        for t in ORIGINS:
            b = stock.batches(t, source)
            b = b[b["status"].isin(["pick_first", "in_line", "at_risk"])]
            b = b[b["date_60"] <= snaps.max()]                         # outcome observable in the data
            tp = fp = fn = tn = 0
            for r in b.itertuples():
                later = snaps[snaps >= r.date_60]
                obs = _snapshot_qty(str(later.min().date())).get((r.cnf_code, r.sku_code, r.batch_no), 0.0)
                still, flagged = bool(obs > 0), r.status == "at_risk"
                tp += flagged and still
                fp += flagged and not still
                fn += (not flagged) and still
                tn += (not flagged) and (not still)
            tp, fp, fn, tn = int(tp), int(fp), int(fn), int(tn)
            tot = [tot[0] + tp, tot[1] + fp, tot[2] + fn, tot[3] + tn]
            out.append({"origin": t, "evaluable_batches": int(len(b)), "tp": tp, "fp": fp, "fn": fn, "tn": tn,
                        "precision": round(tp / (tp + fp), 3) if tp + fp else None, "recall": round(tp / (tp + fn), 3) if tp + fn else None})
        summary[source] = {"by_origin": out, "flagged": tot[0] + tot[1], "precision": round(tot[0] / (tot[0] + tot[1]), 3),
                           "recall": round(tot[0] / (tot[0] + tot[2]), 3)}
    save("at_risk_flag", summary)
    # The finding (plan step 3): on real demand the flag is more often right but catches far fewer leftovers.
    assert summary["invoices"]["precision"] > summary["report"]["precision"]
    assert summary["invoices"]["recall"] < summary["report"]["recall"]


def test_not_moving_watch_signal():
    """TC-BKT-007 | Backtest (chronological) | plan step 3 | 'Not moving since last snapshot' alone and with the forecast: still in stock at the 60% date?"""
    from agent import stock
    snaps = pd.to_datetime(["2026-03-31", "2026-04-30", "2026-05-31", "2026-06-30", "2026-07-31", "2026-08-31", "2026-09-30"])
    tally = {k: [0, 0, 0] for k in ("forecast", "not_moving", "either")}
    for t in ORIGINS:
        b = stock.batches(t)
        b = b[b["status"].isin(["pick_first", "in_line", "at_risk"]) & (b["date_60"] <= snaps.max())]
        for r in b.itertuples():
            later = snaps[snaps >= r.date_60]
            still = bool(_snapshot_qty(str(later.min().date())).get((r.cnf_code, r.sku_code, r.batch_no), 0.0) > 0)
            sig = {"forecast": r.status == "at_risk", "not_moving": bool(r.not_moving)}
            sig["either"] = sig["forecast"] or sig["not_moving"]
            for k, f in sig.items():
                tally[k][0] += f and still
                tally[k][1] += f and not still
                tally[k][2] += (not f) and still
    out = {k: {"flagged": int(v[0] + v[1]), "precision": round(v[0] / max(1, v[0] + v[1]), 3), "recall": round(v[0] / max(1, v[0] + v[2]), 3)}
           for k, v in tally.items()}
    save("not_moving_watch", out)
    assert out["either"]["recall"] > out["forecast"]["recall"]  # the watch list catches what the forecast misses


def test_allocation_backtest():
    """TC-BKT-008 | Backtest (chronological) | plan step 5 | Replay Mar-Aug 2026: top-ups planned at T, served next month's normal orders; current vs FY25 shares vs the old method"""
    from agent import allocation_backtest as ab
    out = ab.run()
    save("allocation", {k: out[k] for k in ("orders_inr", "actual_unfilled_inr", "summary", "unfilled_by_cfa", "limits")} |
         {"returns": {k: out["returns"][k] for k in ("count", "value_inr", "short_after_return_inr")}, "by_month": out["by_month"]})
    s = out["summary"]
    assert s["current"]["unfilled_inr"] < s["fy25"]["unfilled_inr"] < s["old_report"]["unfilled_inr"]
    assert out["returns"]["short_after_return_inr"] == 0


def test_money_is_exact_to_the_paisa():
    """TC-BKT-005 | Financial precision | CO-POL-014 5.7 | Every credit = qty x PTS to the paisa (Decimal half-up), no float noise, never negative"""
    from fastapi.testclient import TestClient

    from agent.tools import table
    from app import app
    pts = table("sku_master.csv").set_index("sku_code")["pts_inr"]
    assert all(len(p.split(".")[1]) <= 2 for p in pts if "." in p)  # PTS has at most 2 decimals, so qty x PTS is exact
    c = TestClient(app)
    checked = 0
    for cl in c.get("/api/claims?status=Pending&limit=120").json():
        ln = c.post("/api/claim/register", json={"claim_no": cl["claim_no"]}).json()["lines"][0]
        rec = ln["recommendation"]
        if rec["action"] in ("approve", "approve_part"):
            exp = (Decimal(str(rec["qty"])) * Decimal(pts[ln["claim"]["sku_code"]])).quantize(Decimal("0.01"), ROUND_HALF_UP)
            assert Decimal(str(rec["credit_inr"])) == exp
            checked += 1
    assert checked > 50


@pytest.mark.parametrize("received,expected", [("2026-10-20", "2026-11-03"),   # Tue -> 10 working days
                                               ("2026-10-23", "2026-11-06"),   # Fri
                                               ("2026-10-24", "2026-11-06"),   # Sat: counting starts Mon
                                               ("2026-12-31", "2027-01-14")])  # year boundary
def test_working_day_due_dates(received, expected):
    """TC-BKT-006 | Date handling | CO-POL-014 5.6 | 10-working-day verification date across weekends and the year end"""
    from datetime import date

    from agent import store
    assert store._working_days_after(date.fromisoformat(received), 10).isoformat() == expected
