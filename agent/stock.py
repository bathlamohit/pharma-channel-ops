"""Expiry and dispatch plan: what each CFA should pick, block, or send back, batch by batch.

Plain pandas, no model (ADR 0014). Stock is the latest snapshot (policy.SNAPSHOT_DATE).
For every batch on hand, in oldest-expiry-first order per CFA and product (CF 6.3):

  block         under 60 days to expiry: blocked, never picked, destroyed under witness
                (CO-POL-014 7.1, 7.2; CF Sch 2 2.3.4, 2.7)
  short_dated   under 60% of shelf life left: a stockist may refuse it (CO-POL-014 7.1);
                bill only with the stockist's agreement
  at_risk       still sellable today, but at this CFA's normal demand part of it will not
                sell before it falls under 60% of shelf life; suggest a return to the CDC for
                CFAs that can sell it (CF Sch 2 2.5), or a push in dispatch
  pick_first    the batch the next order should be picked from
  in_line       sellable in time behind an older batch

Projection: the CFA sells its normal monthly demand (from invoices, agent/demand.py), oldest batch first. A batch can sell
until its 60% date (expiry - 60% of shelf life). Packs still left then are at risk. Blocked and
short-dated batches are assumed not to take orders (they need agreement or are blocked).
"""
import copy
from functools import lru_cache

import pandas as pd

from agent import policy
from agent.tools import _stock_rows, cite, group_lists, stock_on_hand, table

DAYS_PER_MONTH = 30.44
ORDER = {"block": 0, "short_dated": 1, "at_risk": 2, "pick_first": 3, "in_line": 4}


def _skus() -> pd.DataFrame:
    s = table("sku_master.csv")[["sku_code", "product_description", "shelf_life_months", "pts_inr"]].copy()
    s[["shelf_life_months", "pts_inr"]] = s[["shelf_life_months", "pts_inr"]].astype(float)
    return s


SOURCES = ("invoices", "dispatched", "report")


def _rate(as_of: pd.Timestamp, source: str) -> pd.Series:
    """How fast each C&F sells each SKU, packs a month, per plan step 3:
    invoices    normal demand from agent/demand.py (non-scheme dispatches; the client's definition). Default.
    dispatched  all dispatches incl. scheme loading, last 3 months (for the backtest comparison only)
    report      the SAP field avg_monthly_outward_packs (unreliable per the client; backtest comparison only)"""
    from agent import demand
    if source == "invoices":
        return demand.demand(str(as_of.date()))["normal_month"]
    if source == "dispatched":
        return demand.demand(str(as_of.date()))["dispatched_month"]
    st = table("cnf_stock_snapshot.csv")
    st = st[st["snapshot_date"] == as_of]
    return st.groupby(["cnf_code", "sku_code"])["avg_monthly_outward_packs"].first().astype(float)


@lru_cache(maxsize=16)
def batches(as_of: str | None = None, source: str = "invoices") -> pd.DataFrame:
    """Every batch on hand at the snapshot, with its status and suggested action. The selling rate
    comes from invoices (normal demand), not the SAP outward field (client: unreliable)."""
    if source not in SOURCES:
        raise ValueError(f"source is one of {SOURCES}")
    st = table("cnf_stock_snapshot.csv")
    # as_of: an earlier snapshot date (YYYY-MM-DD), used by the chronological backtest; default latest
    as_of = pd.Timestamp(as_of) if as_of else st["snapshot_date"].max()
    st = _stock_rows()
    st = st[(st["snapshot_date"] == as_of) & (st["batch_no"] != "")].copy()
    st["src_line"] = st["src_line"].astype(int)
    # a batch can sit on more than one snapshot row (bins): one row per CFA, product and batch
    by = ["cnf_code", "cnf_city", "sku_code", "batch_no"]
    lists = group_lists(st, by, "src_line")
    st = st.groupby(by, as_index=False).agg(expiry_date=("expiry_date", "first"), qty=("qty", "sum"))
    st["src_lines"] = lists
    rate = _rate(as_of, source)
    st["outward"] = [float(rate.get((c, k), 0.0)) for c, k in zip(st["cnf_code"], st["sku_code"])]
    st = st[st["qty"] > 0].merge(_skus(), on="sku_code")
    st["days_left"] = (st["expiry_date"] - as_of).dt.days
    st["shelf_share"] = st["days_left"] / (st["shelf_life_months"] * DAYS_PER_MONTH)
    st["date_60"] = st["expiry_date"] - pd.to_timedelta(
        policy.MIN_SHELF_LIFE_SHARE.value * st["shelf_life_months"] * DAYS_PER_MONTH, unit="D")
    st["months_sellable"] = ((st["date_60"] - as_of).dt.days / DAYS_PER_MONTH).clip(lower=0)
    st["value_inr"] = (st["qty"] * st["pts_inr"]).round(2)
    st = st.sort_values(["cnf_code", "sku_code", "expiry_date", "batch_no"]).reset_index(drop=True)

    status, sellable, first_seen = [], [], set()
    for _, g in st.groupby(["cnf_code", "sku_code"], sort=False):
        queue = 0.0  # packs ahead of this batch in the pick order
        for r in g.itertuples():
            i = r.Index
            if r.days_left < policy.BLOCK_DAYS.value:
                status.append((i, "block")); sellable.append((i, 0.0))
                continue
            if r.shelf_share < policy.MIN_SHELF_LIFE_SHARE.value:
                status.append((i, "short_dated")); sellable.append((i, 0.0))
                continue
            can = min(r.qty, max(0.0, r.outward * r.months_sellable - queue))
            queue += r.qty
            sellable.append((i, can))
            key = (r.cnf_code, r.sku_code)
            if can < r.qty - 0.5:
                status.append((i, "at_risk"))
            elif key not in first_seen:
                status.append((i, "pick_first"))
            else:
                status.append((i, "in_line"))
            first_seen.add(key)
    st["status"] = pd.Series(dict(status))
    st["sellable_qty"] = pd.Series(dict(sellable)).round()
    st["unsold_qty"] = (st["qty"] - st["sellable_qty"]).where(st["status"] == "at_risk", 0).round()
    # the first sellable batch is still the one to pick, even when part of it is at risk
    firsts = st[st["status"].isin(["pick_first", "at_risk", "in_line"])].groupby(["cnf_code", "sku_code"]).head(1).index
    st["pick_now"] = st.index.isin(firsts)
    st["as_of"] = as_of
    st["src_line"] = st["src_lines"].str[0]
    # Watch list (plan step 3): sellable batches that barely sold since the previous snapshot.
    snaps = table("cnf_stock_snapshot.csv")["snapshot_date"]
    earlier = snaps[snaps < as_of]
    st["prev_date"] = earlier.max() if len(earlier) else pd.NaT
    if len(earlier):
        prev = stock_on_hand(earlier.max(), ("cnf_code", "sku_code", "batch_no"))
        st["prev_qty"] = [prev.get((c, k, n)) for c, k, n in zip(st["cnf_code"], st["sku_code"], st["batch_no"])]
    else:
        st["prev_qty"] = None
    st["prev_qty"] = pd.to_numeric(st["prev_qty"], errors="coerce")
    sold = (st["prev_qty"] - st["qty"]) / st["prev_qty"]
    st["sold_share"] = sold.round(3)
    st["not_moving"] = (st["status"].isin(["pick_first", "in_line", "at_risk"]) & st["prev_qty"].notna()
                        & (st["prev_qty"] > 0) & (sold < policy.NOT_MOVING_SOLD_SHARE.value))
    return st


def _cdc_takers(b: pd.Series, all_b: pd.DataFrame) -> list[dict]:
    """CFAs that could sell this batch after a return to the CDC (CF Sch 2 2.5): their outward
    over the batch's sellable months, after transit, less their own sellable stock of the product."""
    transit = policy.CDC_RETURN_DAYS.value / DAYS_PER_MONTH
    months = max(0.0, b["months_sellable"] - transit)
    out = []
    for cfa, g in all_b[(all_b["sku_code"] == b["sku_code"]) & (all_b["cnf_code"] != b["cnf_code"])].groupby("cnf_code"):
        own = g[g["status"].isin(["pick_first", "in_line", "at_risk"])]["sellable_qty"].sum()
        outward = _outward(cfa, b["sku_code"])
        room = outward * months - own
        if outward > 0 and room >= 1:
            out.append({"cnf_code": cfa, "cnf_city": g["cnf_city"].iloc[0], "can_take": int(min(room, b["unsold_qty"]))})
    # CFAs with outward but none of this batch's product on hand
    for cfa, city, outward in _outward_rows(b["sku_code"]):
        if cfa != b["cnf_code"] and cfa not in {o["cnf_code"] for o in out} and \
                cfa not in set(all_b[all_b["sku_code"] == b["sku_code"]]["cnf_code"]) and outward * months >= 1:
            out.append({"cnf_code": cfa, "cnf_city": city, "can_take": int(min(outward * months, b["unsold_qty"]))})
    return sorted(out, key=lambda o: -o["can_take"])[:3]


@lru_cache(maxsize=1)
def _outward_table() -> pd.DataFrame:
    """Normal demand per C&F and SKU (from invoices), with the C&F's city."""
    from agent import demand
    d = demand.demand()["normal_month"].rename("avg_monthly_outward_packs").reset_index()
    st = table("cnf_stock_snapshot.csv")
    d["cnf_city"] = d["cnf_code"].map(dict(zip(st["cnf_code"], st["cnf_city"])))
    return d[["cnf_code", "cnf_city", "sku_code", "avg_monthly_outward_packs"]]


def _outward(cfa: str, sku: str) -> float:
    t = _outward_table()
    hit = t[(t["cnf_code"] == cfa) & (t["sku_code"] == sku)]["avg_monthly_outward_packs"]
    return float(hit.iloc[0]) if len(hit) else 0.0


def _outward_rows(sku: str):
    t = _outward_table()
    for r in t[t["sku_code"] == sku].itertuples():
        yield r.cnf_code, r.cnf_city, r.avg_monthly_outward_packs


def _what_to_do(b: pd.Series, all_b: pd.DataFrame) -> dict:
    """Plain words for a person at the CFA or in Supply Chain, with the clause."""
    qty, exp = int(b["qty"]), b["expiry_date"].strftime("%d %b %Y")
    if b["status"] == "block":
        return {"title": "Block this batch", "action": "block",
                "why": f"{b['days_left']} days to expiry ({exp}); under 60 days it must not be picked",
                "do": f"Move {qty:,} packs to restricted stock in SAP and add them to this month's destruction list",
                "clause": f"{policy.BLOCK_DAYS.clause}; {policy.DESTRUCTION_CLAUSE}"}
    if b["status"] == "short_dated":
        return {"title": "Bill only with the stockist's agreement", "action": "consent",
                "why": f"{b['shelf_share']:.0%} of shelf life left; a stockist may refuse stock under 60%",
                "do": f"Offer the {qty:,} packs to stockists who agree in writing; block on reaching 60 days to expiry "
                      f"({(b['expiry_date'] - pd.Timedelta(days=60)).strftime('%d %b %Y')})",
                "clause": policy.MIN_SHELF_LIFE_SHARE.clause}
    if b["status"] == "at_risk":
        takers = _cdc_takers(b, all_b)
        by = b["date_60"].strftime("%d %b %Y")
        unsold = int(b["unsold_qty"])
        # The client's return rules (22 Nov 2026), the same as Allocation's: the batch must keep 60%
        # shelf life and 60 days after 14 days in transit, and the return must be worth >= Rs 5 lakh.
        after = b["days_left"] - policy.RETURN_TRANSIT_DAYS.value
        keeps = after / (b["shelf_life_months"] * DAYS_PER_MONTH) >= policy.MIN_SHELF_LIFE_SHARE.value and after >= policy.BLOCK_DAYS.value
        worth = min(unsold, sum(t["can_take"] for t in takers)) * b["pts_inr"] >= policy.RETURN_MIN_VALUE_INR.value if takers else False
        if takers and keeps and worth:
            names = ", ".join(f"{t['cnf_city']} ({t['can_take']:,})" for t in takers)
            send = min(unsold, sum(t["can_take"] for t in takers))
            rest = unsold - send
            tail = f"; push the other {rest:,} packs in dispatch here" if rest else ""
            return {"title": "Return the excess to the CDC", "action": "cdc_return", "takers": takers,
                    "return_qty": send,
                    "why": f"At its normal demand of {int(b['outward']):,} packs a month, about {unsold:,} of {qty:,} packs will not sell "
                           f"here before {by}, when it drops under 60% of shelf life",
                    "do": f"Ask the Regional Distribution Manager to request a CDC return of {send:,} packs, for "
                          f"{names}; the Head of Supply Chain approves{tail}",
                    "clause": f"{policy.CDC_RETURN_DAYS.clause}; {policy.MIN_SHELF_LIFE_SHARE.clause}"}
        reason = ("no other C&F sells enough of this product to take them" if not takers else
                  "a return is not allowed: under Rs 5 lakh, or the batch would fall under 60% shelf life in transit")
        return {"title": "Push this batch in dispatch", "action": "push",
                "why": f"At its normal demand of {int(b['outward']):,} packs a month, about {unsold:,} of {qty:,} packs will not "
                       f"sell here before {by}; {reason}",
                "do": "Keep it first in the pick order and tell Sales which stockists can take more",
                "clause": policy.FEFO_CLAUSE}
    if b["status"] == "pick_first":
        return {"title": "Pick from this batch first", "action": "pick",
                "why": f"Oldest sellable batch of this product here (expires {exp})",
                "do": "Pick every order line for this product from this batch until it runs out",
                "clause": policy.FEFO_CLAUSE}
    return {"title": "Next in line", "action": "none", "why": f"Sells in time behind the older batch (expires {exp})",
            "do": "No action", "clause": policy.FEFO_CLAUSE}


def _act_by(b: pd.Series, action: str) -> str | None:
    """The last day the action still helps: block now; offer short-dated stock before it must be
    blocked; request a CDC return early enough for the transit before the 60% date."""
    if b["status"] == "block":
        return b["as_of"].strftime("%Y-%m-%d")
    if b["status"] == "short_dated":
        return (b["expiry_date"] - pd.Timedelta(days=policy.BLOCK_DAYS.value)).strftime("%Y-%m-%d")
    if b["status"] == "at_risk":
        transit = policy.CDC_RETURN_DAYS.value if action == "cdc_return" else 0
        return (b["date_60"] - pd.Timedelta(days=transit)).strftime("%Y-%m-%d")
    return None


def _watch(b: pd.Series) -> dict:
    """Plain words for the not-moving watch list. In the backtest about half of these were still in
    stock at their 60% date: 46% when it was the batch to pick first, 71% when it sat behind an older one."""
    since = b["prev_date"].strftime("%d %b")
    sold = max(0, int(round(b["prev_qty"] - b["qty"])))
    expect = int(round(b["outward"] * ((b["as_of"] - b["prev_date"]).days / DAYS_PER_MONTH)))
    why = (f"Sold {sold:,} of {int(b['prev_qty']):,} packs since {since} ({max(0.0, b['sold_share']):.0%}); "
           f"its normal demand here is {int(b['outward']):,} packs a month")
    if b["pick_now"]:
        return {"title": "Batch to pick first is not moving", "why": why + f", so about {expect:,} should have gone out",
                "do": "Check with the CFA that orders are being picked from this batch (CF 6.3). If they are, demand is low: "
                      "push it in dispatch before it drops under 60% shelf life",
                "clause": policy.NOT_MOVING_SOLD_SHARE.clause}
    return {"title": "Waiting behind an older batch", "why": why + "; an older batch is ahead of it in the pick order",
            "do": "Watch it: it moves only once the older batch is used. If the older batch is not moving either, check picking at the CFA",
            "clause": policy.NOT_MOVING_SOLD_SHARE.clause}


def _row(b: pd.Series, all_b: pd.DataFrame) -> dict:
    what = _what_to_do(b, all_b)
    return {"act_by": _act_by(b, what["action"]),
        "cnf_code": b["cnf_code"], "cnf_city": b["cnf_city"], "sku_code": b["sku_code"],
        "product": b["product_description"], "batch_no": b["batch_no"],
        "expiry_date": b["expiry_date"].strftime("%Y-%m-%d"), "days_left": int(b["days_left"]),
        "shelf_share": round(float(b["shelf_share"]), 3), "qty": int(b["qty"]), "value_inr": float(b["value_inr"]),
        "outward_per_month": int(b["outward"]), "status": b["status"], "unsold_qty": int(b["unsold_qty"]),
        "pick_now": bool(b["pick_now"]), "src_lines": b["src_lines"], **what,
        "not_moving": bool(b["not_moving"]),
        "prev_qty": None if pd.isna(b["prev_qty"]) else int(b["prev_qty"]),
        "sold_share": None if pd.isna(b["sold_share"]) else float(b["sold_share"]),
    }


@lru_cache(maxsize=1)
def _overview() -> dict:
    """One card per CFA: stock value, value needing action, and the batch-order alert."""
    from agent.watch import fefo_share
    b = batches()
    share = fefo_share().iloc[-1]
    cards = []
    for (cfa, city), g in b.groupby(["cnf_code", "cnf_city"]):
        act = g[g["status"].isin(["block", "short_dated", "at_risk"])]
        cards.append({
            "cnf_code": cfa, "cnf_city": city, "stock_value_inr": round(float(g["value_inr"].sum()), 2),
            "batches": int(len(g)),
            "to_block": int((g["status"] == "block").sum()),
            "short_dated": int((g["status"] == "short_dated").sum()),
            "at_risk": int((g["status"] == "at_risk").sum()),
            "not_moving": int(g["not_moving"].sum()),
            "not_moving_value_inr": round(float(g.loc[g["not_moving"], "value_inr"].sum()), 2),
            "action_value_inr": round(float(act["value_inr"].sum()), 2),
            "under_60_value_inr": round(float(g[g["shelf_share"] < policy.MIN_SHELF_LIFE_SHARE.value]["value_inr"].sum()), 2),
            "fefo_share": round(float(share.get(cfa, 0.0)), 3),
            "fefo_alert": bool(share.get(cfa, 0.0) > policy.FEFO_ALERT_SHARE.value),
        })
    return {"as_of": b["as_of"].iloc[0].strftime("%Y-%m-%d"), "cards": sorted(cards, key=lambda c: -c["action_value_inr"]),
            "rules": {"min_shelf_share": policy.MIN_SHELF_LIFE_SHARE.value, "block_days": policy.BLOCK_DAYS.value,
                      "fefo_alert_share": policy.FEFO_ALERT_SHARE.value}}


@lru_cache(maxsize=16)
def _plan(cfa: str) -> dict:
    """Everything one CFA has to do, most urgent first, plus its pick list and batch-order check."""
    from agent.watch import fefo_lines, fefo_share
    b = batches()
    mine = b[b["cnf_code"] == cfa]
    if mine.empty:
        raise ValueError(f"No stock for {cfa!r} at the latest snapshot")
    rows = [_row(r, b) for _, r in mine.iterrows()]
    todo = sorted([r for r in rows if r["status"] in ("block", "short_dated", "at_risk")],
                  key=lambda r: (r["act_by"], ORDER[r["status"]], -r["value_inr"]))
    pick = []
    for sku, g in sorted(((k, [r for r in rows if r["sku_code"] == k]) for k in {r["sku_code"] for r in rows}),
                         key=lambda kv: kv[1][0]["product"]):
        pick.append({"sku_code": sku, "product": g[0]["product"], "outward_per_month": g[0]["outward_per_month"],
                     "stock_packs": sum(r["qty"] for r in g),
                     "cover_months": round(sum(r["qty"] for r in g) / g[0]["outward_per_month"], 1) if g[0]["outward_per_month"] else None,
                     "batches": g})
    share = fefo_share()[cfa].dropna()
    lines = fefo_lines()
    recent = lines[(lines["cnf_code"] == cfa) & lines["inverted"] & (lines["month"] > share.index[-1] - 3)]
    skipped = recent.groupby("sku_code")["inverted_packs"].sum().sort_values(ascending=False).head(5)
    fefo = {
        "share_by_month": {str(m): round(float(v), 3) for m, v in share.tail(12).items()},
        "latest": round(float(share.iloc[-1]), 3), "alert": bool(share.iloc[-1] > policy.FEFO_ALERT_SHARE.value),
        "threshold": policy.FEFO_ALERT_SHARE.value, "clause": policy.FEFO_ALERT_SHARE.clause,
        "top_products": [{"sku_code": k, "product": _skus().set_index("sku_code").loc[k, "product_description"],
                          "packs": int(v)} for k, v in skipped.items()],
        "citations": [cite("primary_sales.csv", recent)] if len(recent) else [],
    }
    watch = []
    for _, r in mine[mine["not_moving"]].iterrows():
        row = _row(r, b)
        watch.append({**row, **_watch(r), "watch_action": "check"})
    watch.sort(key=lambda w: (not w["pick_now"], w["act_by"] or w["expiry_date"], -w["value_inr"]))
    prev = mine["prev_date"].iloc[0]
    return {"cnf_code": cfa, "cnf_city": mine["cnf_city"].iloc[0], "as_of": mine["as_of"].iloc[0].strftime("%Y-%m-%d"),
            "todo": todo, "pick_list": pick, "fefo": fefo,
            "watch": watch, "watch_since": None if pd.isna(prev) else prev.strftime("%Y-%m-%d"),
            "watch_note": "Backtest: about half of these were still in stock at their 60% date (46% when it was the batch to "
                          "pick first, 71% when behind an older batch). Together with the forecast this catches 43% of leftovers.",
            "citations": [{"file": "cnf_stock_snapshot.csv", "rows": [n for ls in mine["src_lines"] for n in ls],
                           "snapshot": mine["as_of"].iloc[0].strftime("%Y-%m-%d")}]}

# --- Caching (QA 21 Nov 2026, D-04) ------------------------------------------------------
# These results depend only on the data extract, which is loaded once per process (tools.table).
# They are computed once and handed out as copies, so callers can add keys without changing the cache.
def overview() -> dict:
    """One card per CFA: stock value, value needing action, and the batch-order alert."""
    return copy.deepcopy(_overview())


def plan(cfa: str) -> dict:
    """Everything one CFA has to do, most urgent first, plus its pick list and batch-order check."""
    return copy.deepcopy(_plan(cfa))
