"""Project Sankalp claim desk and watch workflow (Final Plan, section 4; board v2).

Top graph
    route_request ─ email ───► extract_claim ─┬─ claim lines ───► check_lines ─┐
                 │                             ├─ status / other ─► draft_reply ─┤
                 │                             └─ nothing usable ─► needs_person ┤
                 ├─ register ─────────────────────────────────────► check_lines ─┤
                 └─ watch ───► chosen views (parallel) ─► build_digest ──────────┤
       check_lines / needs_person ─► explain ─► cite_and_format ─► audit_log ─► END
       draft_reply / build_digest ─────────────► cite_and_format

Claim subgraph (run by check_lines once per claim line)
    resolve_records ─ found ─► 8 checks (parallel) ─► decide_route ─► END
                    └ not found or bad input ─► needs_person ─► END

Deterministic first (ADR 0012): the rules reader reads emails; the model is asked only for an
email the reader recognises nothing in. Explanations, replies and letters are templates.
The graph ends at a recommendation; a person decides through POST /api/decision.
"""
from langgraph.graph import END, START, StateGraph

from agent import rules
from agent.audit import audit_log
from agent.claim_nodes import (decide_route, draft_reply, explain, extract_claim, form_to_claims, make_check_lines,
                               make_check_node, needs_person, resolve_records, route_email, route_records)
from agent.guard import cite_and_format
from agent.state import ClaimState, SankalpState
from agent.watch import TAB_VIEWS, VIEWS, build_digest

CLAIM_FIELDS = ("claim_no", "claim_date", "stockist_code", "cnf_code", "sku_code", "batch_no",
                "expiry_date_as_claimed", "qty_claimed", "claim_value_inr", "claim_type", "original_invoice_ref",
                "status", "credit_note_no")


def build_claim_graph():
    b = StateGraph(ClaimState)
    b.add_node("resolve_records", resolve_records)
    b.add_node("needs_person", needs_person)
    for name in rules.CHECKS:
        b.add_node(name, make_check_node(name))
    b.add_node("decide_route", decide_route)
    b.add_edge(START, "resolve_records")
    b.add_conditional_edges("resolve_records", route_records, ["needs_person", *rules.CHECKS])
    b.add_edge(list(rules.CHECKS), "decide_route")  # join: waits for all eight
    b.add_edge("decide_route", END)
    b.add_edge("needs_person", END)
    return b.compile()


def route_request(state: SankalpState) -> dict:
    """Route by the tab the user pressed, not by a model. A register row becomes one claim line."""
    if state["entry"] == "register":
        row = state["raw_input"]
        claim = {k: row.get(k) for k in CLAIM_FIELDS}
        claim["invoice_ref"] = claim.pop("original_invoice_ref")
        return {"claims": [claim]}
    if state["entry"] == "form":
        return {"claims": form_to_claims(state["raw_input"]), "email_kind": "claim"}
    if state["entry"] == "watch":
        return {"views": state["raw_input"].get("views") or TAB_VIEWS["weekly"]}
    return {}


def pick_path(state: SankalpState):
    if state["entry"] == "email":
        return "extract_claim"
    if state["entry"] in ("register", "form"):
        return "check_lines"
    return [v for v in state["views"] if v in VIEWS]


def build_graph():
    b = StateGraph(SankalpState)

    b.add_node("route_request", route_request)
    b.add_node("extract_claim", extract_claim)
    b.add_node("draft_reply", draft_reply)
    b.add_node("check_lines", make_check_lines(build_claim_graph()))
    b.add_node("needs_person", needs_person)
    b.add_node("explain", explain)
    for name, fn in VIEWS.items():
        b.add_node(name, fn)
    b.add_node("build_digest", build_digest)
    b.add_node("cite_and_format", cite_and_format)
    b.add_node("audit_log", audit_log)

    b.add_edge(START, "route_request")
    b.add_conditional_edges("route_request", pick_path, ["extract_claim", "check_lines", *VIEWS])

    # Claim path
    b.add_conditional_edges("extract_claim", route_email, ["check_lines", "draft_reply", "needs_person"])
    b.add_edge("check_lines", "explain")
    b.add_edge("needs_person", "explain")
    b.add_edge("explain", "cite_and_format")
    b.add_edge("draft_reply", "cite_and_format")

    # Watch path: each chosen view feeds the digest; it runs once they finish
    for name in VIEWS:
        b.add_edge(name, "build_digest")
    b.add_edge("build_digest", "cite_and_format")

    b.add_edge("cite_and_format", "audit_log")
    b.add_edge("audit_log", END)
    return b.compile()


graph = build_graph()


def run(entry: str, raw_input: dict) -> dict:
    return graph.invoke({"entry": entry, "raw_input": raw_input})
