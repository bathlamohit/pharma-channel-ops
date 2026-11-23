"""QA: recompute the headline figures from data/raw/ with independent code, and compare them with
what the API serves and with the verified analysis.

    python scripts/qa_check.py

Independent means: this file imports nothing from agent/ to compute. It cleans the raw CSVs
itself (date formats, code spellings, exact duplicates, blank values) and applies the metric
definitions written in ADR 0009. Only the comparison step calls the API (FastAPI TestClient),
with the claims store, action log and audit log pointed at a temporary folder.
Exit code 1 if any check fails.
"""
import math
import os
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
TMP = Path(tempfile.mkdtemp(prefix="sankalp-qa-"))
os.environ.update(CLAIMS_STORE=str(TMP / "claims.jsonl"), STOCK_ACTIONS=str(TMP / "actions.jsonl"),
                  AUDIT_LOG=str(TMP / "audit.jsonl"))
SNAP = pd.Timestamp("2026-09-30")
MONTH = 30.44


# --- independent cleaning --------------------------------------------------------------
def date(s: pd.Series) -> pd.Series:
    s = s.fillna("").astype(str).str.strip()
    out = pd.to_datetime(s, format="%d-%m-%Y", errors="coerce")
    for fmt in ("%Y-%m-%d", "%d-%b-%Y"):
        out = out.fillna(pd.to_datetime(s, format=fmt, errors="coerce"))
    return out


def num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s.fillna("").astype(str).str.replace(",", "").str.strip(), errors="coerce")


def code(s: pd.Series) -> pd.Series:
    return s.fillna("").astype(str).str.strip().str.upper()


def raw(name: str) -> pd.DataFrame:
    df = pd.read_csv(RAW / name, dtype=str, keep_default_na=False)
    return df.drop_duplicates()


sku = raw("sku_master.csv")
sku["pts"] = num(sku["pts_inr"])
sku["shelf"] = num(sku["shelf_life_months"])
PTS, SHELF = sku.set_index("sku_code")["pts"], sku.set_index("sku_code")["shelf"]

batch = raw("batch_master.csv")
batch["batch_no"] = code(batch["batch_no"])
batch["expiry"] = date(batch["expiry_date"])
EXP = batch.set_index("batch_no")["expiry"]

claims = raw("expiry_claims.csv")
for c in ("stockist_code", "batch_no", "cnf_code"):
    claims[c] = code(claims[c])
claims["sku_code"] = code(claims["sku_code"]).str.replace("-", "", regex=False)
claims["claim_date"] = date(claims["claim_date"])
claims["cn_date"] = date(claims["credit_note_date"])
claims["qty"] = num(claims["qty_claimed"])
claims["value"] = num(claims["claim_value_inr"])
claims["value"] = claims["value"].fillna((claims["qty"] * claims["sku_code"].map(PTS)).round(2))

sales = raw("primary_sales.csv")
for c in ("stockist_code", "batch_no"):
    sales[c] = code(sales[c])
sales["sku_code"] = code(sales["sku_code"]).str.replace("-", "", regex=False)
sales["cnf_code"] = code(sales["cnf_code"]).str.replace(r"^CF(?=[A-Z]\d)", "CF-", regex=True)
sales["date"] = date(sales["invoice_date"])
for c in ("ordered_qty", "invoiced_qty", "free_qty", "pts_inr", "net_value_inr"):
    sales[c] = num(sales[c])
sales["scheme"] = sales["scheme_code"].str.strip().where(~sales["scheme_code"].str.strip().isin(["", "NA", "-"]), "")

snap = raw("cnf_stock_snapshot.csv")
snap["cnf_code"] = code(snap["cnf_code"]).str.replace(r"^CF(?=[A-Z]\d)", "CF-", regex=True)
snap["sku_code"] = code(snap["sku_code"]).str.replace("-", "", regex=False)
snap["batch_no"] = code(snap["batch_no"])
snap["date"] = date(snap["snapshot_date"])
snap["expiry"] = date(snap["expiry_date"]).fillna(snap["batch_no"].map(EXP))
snap["qty"] = num(snap["qty_on_hand_packs"]).fillna(0)
snap["out"] = num(snap["avg_monthly_outward_packs"]).fillna(0)
latest = snap[snap["date"] == snap["date"].max()].copy()


# --- independent figures ----------------------------------------------------------------
def figures() -> dict:
    f = {}
    pend = claims[claims["status"] == "Pending"]
    f["claims.pending_count"] = len(pend)
    f["claims.pending_value_L"] = pend["value"].sum() / 1e5
    f["claims.pending_over_30"] = int(((SNAP - pend["claim_date"]).dt.days > 30).sum())
    cred = claims[claims["status"] == "Credited"]
    days = (cred["cn_date"] - cred["claim_date"]).dt.days
    f["claims.credit_days_mean"] = days.mean()
    f["claims.credit_days_median"] = days.median()
    q1 = claims[claims["claim_date"].between("2026-04-01", "2026-06-30") & (claims["status"] != "Rejected")]
    f["claims.q1_fy27_cr"] = q1["value"].sum() / 1e7

    per = latest.groupby(["cnf_code", "sku_code"]).agg(stock=("qty", "sum"), out=("out", "first")).reset_index()
    per["sv"] = per["stock"] * per["sku_code"].map(PTS)
    per["ov"] = per["out"] * per["sku_code"].map(PTS)
    g = per.groupby("cnf_code")[["sv", "ov"]].sum()
    for cfa, r in g.iterrows():
        f[f"cover.{cfa}"] = r.sv / r.ov
    f["cover.national"] = per["sv"].sum() / per["ov"].sum()
    k = per[per["cnf_code"] == "CF-E01"]
    f["cover.kolkata_above_3m_cr"] = (k["sv"] - 3 * k["ov"]).clip(lower=0).sum() / 1e7
    f["cover.lucknow_zero_skus"] = int((per[per["cnf_code"] == "CF-N02"]["stock"] == 0).sum())
    f["cover.stock_outs_selling"] = int(((per["stock"] == 0) & (per["out"] > 0)).sum())

    lt = latest[latest["qty"] > 0].copy()
    lt["share"] = (lt["expiry"] - SNAP).dt.days / (lt["sku_code"].map(SHELF) * MONTH)
    lt["v"] = lt["qty"] * lt["sku_code"].map(PTS)
    f["expiry.kolkata_under60_cr"] = lt[(lt["cnf_code"] == "CF-E01") & (lt["share"] < 0.6)]["v"].sum() / 1e7
    f["expiry.under60_batches"] = int(lt[lt["share"] < 0.6].groupby(["cnf_code", "sku_code", "batch_no"]).ngroups)
    f["expiry.block_batches"] = int(lt[(lt["expiry"] - SNAP).dt.days < 60].groupby(["cnf_code", "sku_code", "batch_no"]).ngroups)

    s4 = sales[sales["date"] > SNAP - pd.DateOffset(years=1)].copy()
    s4["exp"] = s4["batch_no"].map(EXP)
    s4["share"] = (s4["exp"] - s4["date"]).dt.days / (s4["sku_code"].map(SHELF) * MONTH)
    f["expiry.short_dated_billing_cr"] = s4[s4["share"] < 0.6]["net_value_inr"].sum() / 1e7

    h1 = sales[sales["date"].between("2026-04-01", "2026-09-30")]
    u = h1.groupby(["invoice_no", "sku_code"]).agg(date=("date", "first"), ordered=("ordered_qty", "first"),
                                                   inv=("invoiced_qty", "sum"), free=("free_qty", "sum"),
                                                   pts=("pts_inr", "first")).reset_index()
    u["unfilled"] = (u["ordered"] - u["inv"] - u["free"]).clip(lower=0) * u["pts"]
    win = u["date"].dt.month.isin([3, 6, 9, 12]) & (u["date"].dt.day >= 22)
    f["alloc.unfilled_h1_cr"] = u["unfilled"].sum() / 1e7
    f["alloc.unfilled_outside_cr"] = u.loc[~win, "unfilled"].sum() / 1e7

    l4 = (pd.Timestamp("2025-10-01"), SNAP)
    skus = set(sales.loc[sales["scheme"] != "", "sku_code"])
    sl = sales[sales["date"].between(*l4)]
    cl = claims[claims["claim_date"].between(*l4) & claims["claim_type"].isin(["Near expiry", "Expired"])]
    rate = {}
    for name, inside in (("scheme", True), ("other", False)):
        rate[name] = cl[cl["sku_code"].isin(skus) == inside]["value"].sum() / sl[sl["sku_code"].isin(skus) == inside]["net_value_inr"].sum()
    f["scheme.rate_scheme_pct"] = rate["scheme"] * 100
    f["scheme.rate_other_pct"] = rate["other"] * 100
    f["scheme.excess_cr"] = sl[sl["sku_code"].isin(skus)]["net_value_inr"].sum() * (rate["scheme"] - rate["other"]) / 1e7
    q = sales.assign(fg=sales["free_qty"] * sales["pts_inr"], qt=sales["date"].dt.to_period("Q-MAR"))
    qq = q.groupby("qt").agg(fg=("fg", "sum"), s=("net_value_inr", "sum"))
    f["scheme.over_cap_cr"] = (qq["fg"] - 0.03 * qq["s"]).clip(lower=0).sum() / 1e7
    f["scheme.quarters_over"] = int(((qq["fg"] - 0.03 * qq["s"]) > 0).sum())
    f["scheme.latest_quarter_pct"] = qq["fg"].iloc[-1] / qq["s"].iloc[-1] * 100

    # FEFO: share of packs shipped while the same CFA shipped an older batch of the same SKU in the next 90 days
    sv = sales[(sales["batch_no"] != "")].copy()
    sv["packs"] = sv["invoiced_qty"] + sv["free_qty"]
    sv = sv[sv["packs"] > 0].copy()
    sv["exp"] = sv["batch_no"].map(EXP)
    sv = sv.sort_values("date").reset_index(drop=True)
    inv = np.zeros(len(sv), bool)
    for _, gg in sv.groupby(["cnf_code", "sku_code"]):
        d, e, idx = gg["date"].values, gg["exp"].values, gg.index.values
        for i in range(len(gg)):
            lo, hi = np.searchsorted(d, d[i], "right"), np.searchsorted(d, d[i] + np.timedelta64(90, "D"), "right")
            if lo < hi and (e[lo:hi] < e[i]).any():
                inv[idx[i]] = True
    sv["inv"] = inv
    kq2 = sv[(sv["cnf_code"] == "CF-E01") & sv["date"].between("2026-07-01", "2026-09-30")]
    f["fefo.kolkata_fy27q2_pct"] = (kq2["packs"] * kq2["inv"]).sum() / kq2["packs"].sum() * 100
    return f


VERIFIED = {  # from the Final Plan and evidence log (ADR 0008, 0009)
    "claims.pending_count": 360, "claims.pending_value_L": 95.9, "claims.credit_days_mean": 45,
    "claims.credit_days_median": 42, "claims.q1_fy27_cr": 1.415,
    "cover.CF-E01": 3.31, "cover.CF-N02": 0.32, "cover.national": 1.74, "cover.kolkata_above_3m_cr": 1.66,
    "cover.lucknow_zero_skus": 23, "expiry.kolkata_under60_cr": 1.18, "expiry.short_dated_billing_cr": 6.3,
    "alloc.unfilled_h1_cr": 18.30, "alloc.unfilled_outside_cr": 3.54, "scheme.rate_scheme_pct": 4.25,
    "scheme.rate_other_pct": 0.35, "scheme.excess_cr": 4.76, "scheme.over_cap_cr": 3.954,
    "scheme.latest_quarter_pct": 2.82, "fefo.kolkata_fy27q2_pct": 70.7,
}
TOL = {"claims.pending_value_L": 0.05, "claims.credit_days_mean": 0.5, "claims.credit_days_median": 0.5,
       "claims.q1_fy27_cr": 0.002, "expiry.short_dated_billing_cr": 0.1, "scheme.over_cap_cr": 0.0005,
       "scheme.rate_scheme_pct": 0.005, "scheme.rate_other_pct": 0.005, "fefo.kolkata_fy27q2_pct": 0.05,
       "scheme.latest_quarter_pct": 0.005}


def served() -> dict:
    """The same figures as the app serves them."""
    sys.path.insert(0, str(ROOT))
    from fastapi.testclient import TestClient

    from app import app
    c = TestClient(app)
    a = {}
    dg = c.get("/api/digest").json()
    stats = {s["owner"]: {x["label"]: x for x in s["stats"]} for s in dg["sections"]}
    cf = stats["Commercial Finance"]
    a["claims.pending_count"] = int(cf["Pending claims"]["value"])
    a["claims.pending_value_L"] = float(cf["Pending claims"]["sub"].split()[1])
    a["claims.pending_over_30"] = int(cf["Pending over 30 days"]["value"])
    a["claims.credit_days_mean"] = float(cf["Days to credit note"]["value"])
    a["claims.credit_days_median"] = float(cf["Days to credit note"]["sub"].split()[1].rstrip(";"))
    a["claims.pending_list_len"] = len(c.get("/api/claims?status=Pending&limit=1000").json())

    # Since plan step 2 the screens use demand from invoices; the old (verified) figures are served
    # in the "old" column of the restatement, beside the new ones. These checks keep them honest.
    old = {r["figure"]: r["old"] for r in c.get("/api/allocation/restatement").json()["rows"]}
    city = {"CF-E01": "Kolkata", "CF-N01": "Gurugram", "CF-N02": "Lucknow", "CF-S01": "Chennai", "CF-S02": "Hyderabad", "CF-W01": "Bhiwandi"}
    for cfa, name in city.items():
        a[f"cover.{cfa}"] = old[f"Months of stock, {name}"]
    a["cover.national"] = old["Months of stock, national"]
    a["cover.kolkata_above_3m_cr"] = old["Kolkata stock above 3 months (Rs cr)"]
    a["alloc.unfilled_h1_cr"] = old["Orders not filled, last 6 months (Rs cr)"]
    a["alloc.unfilled_outside_cr"] = old["Of which outside scheme weeks (Rs cr)"]

    so = c.get("/api/stock/overview").json()
    a["expiry.kolkata_under60_cr"] = next(x for x in so["cards"] if x["cnf_code"] == "CF-E01")["under_60_value_inr"] / 1e7
    a["expiry.under60_batches"] = sum(x["short_dated"] + x["to_block"] for x in so["cards"])
    a["expiry.block_batches"] = sum(x["to_block"] for x in so["cards"])
    radar = c.post("/api/watch", json={"tab": "watch"}).json()["watch"]
    sd = radar["short_dated"]["summary"]
    a["expiry.short_dated_billing_cr"] = sum(float(p.split("Rs ")[1].split(" L")[0]) for p in sd.split("; ")) / 100
    a["fefo.kolkata_fy27q2_pct"] = c.get("/api/stock/plan?cfa=CF-E01").json()["fefo"]["latest"] * 100

    sc = c.get("/api/allocation/schemes").json()
    a["scheme.rate_scheme_pct"] = sc["scheme_rate"] * 100
    a["scheme.rate_other_pct"] = sc["other_rate"] * 100
    a["scheme.excess_cr"] = sc["excess_claims_inr"] / 1e7
    a["scheme.over_cap_cr"] = sc["over_cap_inr"] / 1e7
    a["scheme.quarters_over"] = sc["quarters_over"]
    a["scheme.latest_quarter_pct"] = sc["quarters"][-1]["share"] * 100
    return a


def close(x, y, tol) -> bool:
    return x is not None and y is not None and math.isclose(float(x), float(y), abs_tol=tol)


def main() -> int:
    ind, app_ = figures(), served()
    keys = sorted(set(ind) | set(app_) | set(VERIFIED))
    fails = 0
    print(f"{'check':34} {'independent':>12} {'app':>12} {'verified':>10}  result")
    for k in keys:
        i, a, v = ind.get(k), app_.get(k), VERIFIED.get(k)
        tol = TOL.get(k, 0.006)
        ok_app = i is None or a is None or close(i, a, tol)
        ok_ver = v is None or close(i if i is not None else a, v, tol)
        if k == "claims.pending_list_len":
            ok_app = a == ind["claims.pending_count"]
        res = "PASS" if ok_app and ok_ver else "FAIL"
        fails += res == "FAIL"
        fmt = lambda x: "" if x is None else f"{x:.3f}" if isinstance(x, float) else str(x)  # noqa: E731
        print(f"{k:34} {fmt(i):>12} {fmt(a):>12} {fmt(v):>10}  {res}")
    print(f"\n{len(keys) - fails} passed, {fails} failed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
