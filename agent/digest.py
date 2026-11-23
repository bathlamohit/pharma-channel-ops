"""Weekly digest: one page per owner, built from the same plans the work screens use (ADR 0016).

No model. Each owner gets the few numbers that matter, the top things to do (each pointing at
the screen where it is done), and what has been recorded as done. A plain-text version is built
from the same facts so it can be pasted into an email; the tool never sends it.
"""
from datetime import datetime, timezone

import pandas as pd

from agent import allocation, policy, stock, stock_log, store
from agent.tools import cite, table

TOP = 5
SCHEME_STEPS = {"Raised with NSM", "Raised with CFO"}
SHARE_STEPS = {"Share change requested", "Share change approved"}
CFA_STEPS = {"Picking order confirmed", "Raised with CFA"}


def _owner(a: dict) -> str:
    """Batch-level steps and CFA-wide ones are Supply Chain's; product-level moves are Demand Planning's."""
    if a["step"] in SHARE_STEPS:
        return "demand"
    if a["cnf_code"] == "NATIONAL" or a["step"] in SCHEME_STEPS:
        return "schemes"
    if a.get("batch_no") or a["step"] in CFA_STEPS:
        return "supply"
    return "demand"


def _crore(v: float) -> str:
    if abs(v) >= 1e7:
        return f"Rs {v / 1e7:.2f} cr"
    if abs(v) >= 1e5:
        return f"Rs {v / 1e5:.1f} L"
    return f"Rs {v:,.0f}"


def _claims() -> dict:
    c = table("expiry_claims.csv")
    as_of = pd.Timestamp(policy.SNAPSHOT_DATE)
    pending = c[c["status"] == "Pending"].copy()
    pending["age"] = (as_of - pending["claim_date"]).dt.days
    pending["value"] = pending["claim_value_inr"].astype(float)
    limit = int(policy.CLAIM_SETTLE_DAYS.value)
    over = pending[pending["age"] > limit]
    credited = c[c["status"] == "Credited"]
    days = (credited["credit_note_date"] - credited["claim_date"]).dt.days
    new = store.snapshot()  # read-only use
    new_open = [n for n in new if n["status"] in store.OPEN or n["status"] == "Approved"]
    new_late = [n for n in new_open if n["due"]["verify_overdue"] or n["due"]["credit_overdue"]]
    names = table("stockist_master.csv").set_index("stockist_code")["stockist_name"]
    oldest = over.sort_values("age", ascending=False).head(TOP)
    todo = [{"text": f"{r.claim_no} from {names.get(r.stockist_code, r.stockist_code)}: pending {r.age} days, "
                     f"{_crore(r.value)}", "tab": "claims", "ref": r.claim_no} for r in oldest.itertuples()]
    todo = [{"text": f"{n['claim_no']} (new): {n['status']}, "
                     f"{'verification' if n['due']['verify_overdue'] else 'credit note'} overdue", "tab": "claims",
             "ref": n["claim_no"]} for n in new_late[:TOP]] + todo
    return {
        "owner": "Commercial Finance", "screen": "claims", "title": "Claims",
        "stats": [
            {"label": "Pending claims", "value": f"{len(pending)}", "sub": _crore(pending["value"].sum())},
            {"label": f"Pending over {limit} days", "value": f"{len(over)}", "sub": _crore(over["value"].sum()),
             "tone": "bad" if len(over) else ""},
            {"label": "Days to credit note", "value": f"{days.mean():.0f}", "sub": f"median {days.median():.0f}; limit {limit}",
             "tone": "bad" if days.mean() > limit else ""},
            {"label": "New claims open", "value": f"{len(new_open)}", "sub": f"{len(new_late)} overdue" if new_late else "none overdue",
             "tone": "bad" if new_late else ""},
        ],
        "todo": todo[:TOP],
        "done": [{"text": f"{h['status']}: {n['claim_no']}", "by": h["by"], "at": h["at"]}
                 for n in new for h in n["history"] if h["by"] != "system"][-TOP:],
        "citations": [cite("expiry_claims.csv", pending)],
    }


def _supply() -> dict:
    from agent import short_dated
    o = stock.overview()
    sd = short_dated.summary()
    tasks = []
    for card in o["cards"]:
        for t in stock.plan(card["cnf_code"])["todo"]:
            tasks.append({**t, "cnf_city": card["cnf_city"]})
    tasks.sort(key=lambda t: (t["act_by"], -t["value_inr"]))
    act_value = sum(c["action_value_inr"] for c in o["cards"])
    alerts = [c for c in o["cards"] if c["fefo_alert"]]
    done = [a for a in stock_log.actions() if _owner(a) == "supply"]
    return {
        "owner": "Supply Chain", "screen": "watch", "title": "Expiry and dispatch",
        "stats": [
            {"label": "Stock needing action", "value": _crore(act_value), "sub": f"{sum(c['short_dated'] + c['at_risk'] + c['to_block'] for c in o['cards'])} batches"},
            {"label": "Bill with consent only", "value": f"{sum(c['short_dated'] for c in o['cards'])}",
             "sub": f"in stock; already billed under 60% in 4 quarters: {_crore(sd['value_inr'])} ({sd['lines']:,} lines)"},
            {"label": "Will not sell in time", "value": f"{sum(c['at_risk'] for c in o['cards'])}",
             "sub": f"plus {sum(c['not_moving'] for c in o['cards'])} batches not moving since last snapshot "
                    f"({_crore(sum(c['not_moving_value_inr'] for c in o['cards']))})"},
            {"label": "Batch-order alert", "value": ", ".join(c["cnf_city"] for c in alerts) or "None",
             "sub": "; ".join(f"{c['fefo_share']:.0%} out of order" for c in alerts) or "all CFAs under 35%",
             "tone": "bad" if alerts else ""},
        ],
        "todo": [{"text": f"{t['cnf_city']}: {t['title'][0].lower() + t['title'][1:]}, {t['product']} {t['batch_no']}, "
                          f"{t['qty']:,} packs, {_crore(t['value_inr'])}, act by {t['act_by']}",
                  "tab": "watch", "ref": t["cnf_code"]} for t in tasks[:TOP]] +
                [{"text": f"{c['cnf_city']}: raise picking out of order with the CFA ({c['fefo_share']:.0%})",
                  "tab": "watch", "ref": c["cnf_code"]} for c in alerts] +
                [{"text": f"{c['cnf_city']}: check {c['not_moving']} batches not moving since last snapshot "
                          f"({_crore(c['not_moving_value_inr'])})", "tab": "watch", "ref": f"watch:{c['cnf_code']}"}
                 for c in sorted(o["cards"], key=lambda c: -c["not_moving_value_inr"])[:1] if c["not_moving"]] +
                [{"text": f"{c['cnf_city']}: {_crore(c['value_inr'])} billed under 60% shelf life in 4 quarters; main reason "
                          f"{c['main_reason'][0].lower() + c['main_reason'][1:]}. Record whether stockists agreed", "tab": "watch", "ref": f"short:{c['cnf_code']}"}
                 for c in sd["cfas"][:1]],
        "done": [{"text": f"{a['step']}: {a['cnf_code']} {a.get('batch_no') or a.get('sku_code') or ''}".strip(),
                  "by": a["by"], "at": a["at"]} for a in done][-TOP:],
        "as_of": o["as_of"],
    }


def _old(figure: str) -> float:
    return next(r["old"] for r in allocation.restatement() if r["figure"] == figure)


def _demand() -> dict:
    """Allocation on demand from invoices (plan step 2): cover on current shares, top-ups from the
    CDC, returns, and the share change awaiting the client."""
    o = allocation.overview("current")
    n = o["national"]
    by_cover = sorted(o["cards"], key=lambda c: c["cover_months"])
    sh = allocation.shares()
    asked = any(a["step"] == "Share change requested" for a in stock_log.actions("NATIONAL"))
    done = [a for a in stock_log.actions() if _owner(a) == "demand"]
    top = by_cover[:2]
    ret = allocation.returns("current")
    todo = [{"text": f"{c['cnf_city']}: {c['cover_months']} months of stock against 2; top up {_crore(c['top_up_inr'])} from the CDC "
                     f"({c['out_of_stock']} products out of stock)", "tab": "allocation", "ref": c["cnf_code"]} for c in top]
    if not asked:
        moved = sorted(sh["cfas"], key=lambda c: -abs(c["change_pts"]))[:2]
        todo.append({"text": "Ask the client to approve the share change: " + "; ".join(
            f"{c['cnf_city']} {c['fy25_share']:.1%} → {c['current_share']:.1%}" for c in moved), "tab": "allocation", "ref": "shares"})
    todo += [{"text": f"Return {r['return_qty']:,} packs of {r['product']} from {r['cnf_city']} to the CDC ({_crore(r['value_inr'])})",
              "tab": "allocation", "ref": "returns"} for r in ret["returns"][:TOP - len(todo)]]
    return {
        "owner": "Demand Planning", "screen": "allocation", "title": "Allocation",
        "notice": {"text": f"Figures restated on 22 Nov 2026: demand now comes from invoices, not the SAP report's outward "
                           f"field (about half of real dispatches). Months of stock {_old('Months of stock, national')} → "
                           f"{n['cover_months']}; orders not filled {_crore(_old('Orders not filled, last 6 months (Rs cr)') * 1e7)} → "
                           f"{_crore(n['unfilled_6m_inr'])} plus {_crore(n['scheme_cut_6m_inr'])} of scheme orders cut. "
                           "See old, new and reason side by side.", "tab": "allocation", "ref": "changes"},
        "stats": [
            {"label": "Months of stock, national", "value": f"{n['cover_months']}",
             "sub": "target 2; " + ", ".join(f"{c['cnf_city']} {c['cover_months']}" for c in top), "tone": "bad"},
            {"label": "Top-up from the CDC this month", "value": _crore(n["top_up_inr"]),
             "sub": f"{n['top_up_lines']} product lines; assumes the CDC can supply"},
            {"label": "Out of stock", "value": f"{n['out_of_stock']}",
             "sub": "; ".join(f"{c['cnf_city']} {c['out_of_stock']}" for c in sorted(o['cards'], key=lambda c: -c['out_of_stock'])[:2])},
            {"label": "Orders not filled, 6 months", "value": _crore(n["unfilled_6m_inr"]),
             "sub": f"plus {_crore(n['scheme_cut_6m_inr'])} of scheme orders cut", "tone": "bad"},
        ],
        "todo": todo[:TOP],
        "done": [{"text": f"{a['step']}: {a['cnf_code']} {a.get('sku_code') or ''} {a.get('note') or ''}".strip(),
                  "by": a["by"], "at": a["at"]} for a in done][-TOP:],
    }


def _schemes() -> dict:
    s = allocation.schemes()
    raised = [a for a in stock_log.actions("NATIONAL") if a["step"] in SCHEME_STEPS]  # share steps belong to Demand Planning
    latest = s["quarters"][-1]
    return {
        "owner": "NSM and CFO", "screen": "allocation", "title": "Schemes",
        "stats": [
            {"label": "Claims on scheme products", "value": f"{s['scheme_rate']:.2%}", "sub": f"others {s['other_rate']:.2%}",
             "tone": "bad"},
            {"label": "Extra claims, last 4 quarters", "value": _crore(s["excess_claims_inr"]), "sub": "from scheme products"},
            {"label": "Free goods over the 3% cap", "value": _crore(s["over_cap_inr"]),
             "sub": f"in {s['quarters_over']} quarters, {s['cap_clause']}", "tone": "bad"},
            {"label": f"Latest quarter, {latest['quarter']}", "value": f"{latest['share']:.2%}",
             "sub": "of sales as free goods; cap 3%", "tone": "bad" if latest["over_cap_inr"] > 0 else ""},
        ],
        "todo": [{"text": "Review quarter-end scheme terms: scheme products claim about "
                          f"{round(s['scheme_rate'] / s['other_rate'])} times as often ({s['approval_clause']})",
                  "tab": "allocation", "ref": "schemes"}],
        "done": [{"text": a["step"], "by": a["by"], "at": a["at"]} for a in raised][-TOP:],
    }


def as_text(d: dict) -> str:
    """The same digest as plain text for an email. Numbers are the ones on screen."""
    out = [f"Project Sankalp weekly digest, stock and register as of {d['as_of']}", ""]
    for s in d["sections"]:
        out.append(f"{s['title'].upper()} ({s['owner']})")
        if s.get("notice"):
            out.append(f"Note: {s['notice']['text']}")
        out += [f"- {x['label']}: {x['value']}" + (f" ({x['sub']})" if x.get("sub") else "") for x in s["stats"]]
        if s["todo"]:
            out.append("To do:")
            out += [f"  {i}. {t['text']}" for i, t in enumerate(s["todo"], 1)]
        if s["done"]:
            out.append("Done:")
            out += [f"  - {x['text']} ({x['by']})" for x in s["done"]]
        out.append("")
    out.append("Every figure cites its source rows in the pilot. A person signs every credit note.")
    return "\n".join(out)


def build() -> dict:
    sections = [_claims(), _supply(), _demand(), _schemes()]
    d = {"as_of": policy.SNAPSHOT_DATE.isoformat(),
         "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
         "sections": sections}
    d["text"] = as_text(d)
    return d
