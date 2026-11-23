"""Run the check set (tests/check_set.json) through the whole graph.

Offline (always): the rules reader reads every email and the model must never be called
(ADR 0012); the reader's form is also compared with the agreed form for all 30 emails.
Live (only with OPENROUTER_API_KEY set): the real model, now only a fallback reader, is still
compared with the agreed forms so it stays a safe fallback.  Run:  pytest -q -m live
"""
import json
import os
from pathlib import Path

import pytest

import agent.claim_nodes as nodes
from agent import reader, tools
from agent.graph import run
from agent.state import ExtractedEmail

CASES = json.loads((Path(__file__).parent / "check_set.json").read_text())


def no_model():
    raise AssertionError("the model was called; every check-set email must be read by rules")


def email_row(email_id: str) -> dict:
    df = tools.table("claim_emails.csv")
    return df[df["email_id"] == email_id].iloc[0].to_dict()


def non_passing(line: dict) -> list[str]:
    """Checks that failed or were flagged. 'skip' (not applicable) is neither."""
    return sorted(k for k, r in line["checks"].items() if r["outcome"] in ("fail", "flag"))


@pytest.mark.parametrize("case", CASES["emails"], ids=[c["id"] for c in CASES["emails"]])
def test_email(case, monkeypatch):
    monkeypatch.setattr(nodes, "get_llm", no_model)
    out = run("email", email_row(case["id"]))
    assert out["read_by"] == "rules"
    exp = case["expect"]
    assert out["route"] == exp["route"], case["why"]
    if "lines" in exp:
        got = [(ln["route"], non_passing(ln)) for ln in out.get("lines", [])]
        assert got == [(ln["route"], sorted(ln["fails"])) for ln in exp["lines"]], case["why"]
    for fact in exp.get("facts_include", []):
        assert any(fact in f for f in out.get("status_facts", [])), (fact, out.get("status_facts"))
    assert out.get("reply")  # every email gets a draft for a person to send
    for i, line in enumerate(out.get("lines", []), 1):  # code states each route and recommendation
        assert f"Line {i} (" in out["explanation"] and nodes.ROUTE_LABEL[line["route"]] in out["explanation"]
        assert line["recommendation"]["action"] in nodes.ACTION_LABEL
    assert out["audit_id"]


@pytest.mark.parametrize("case", CASES["emails"], ids=[c["id"] for c in CASES["emails"]])
def test_rules_reader_matches_agreed_form(case):
    form = reader.read_email(email_row(case["id"]))
    assert form is not None
    assert _comparable(nodes.clean_form(form).model_dump()) == _comparable(case["form"]), case["why"]


@pytest.mark.parametrize("case", CASES["register"], ids=[c["id"] for c in CASES["register"]])
def test_register(case, monkeypatch):
    monkeypatch.setattr(nodes, "get_llm", no_model)
    df = tools.table("expiry_claims.csv")
    out = run("register", df[df["claim_no"] == case["id"]].iloc[0].to_dict())
    line = out["lines"][0]
    assert line["route"] == case["expect"]["route"], case["why"]
    assert set(case["expect"]["fails_include"]) <= set(non_passing(line)), case["why"]
    if case["expect"]["route"] == "clean":
        assert non_passing(line) == []


def test_eml_017_fails_on_quantity_whatever_the_email_says(monkeypatch):
    monkeypatch.setattr(nodes, "get_llm", no_model)
    line = run("email", email_row("EML-017"))["lines"][0]
    assert line["checks"]["chk_quantity"]["detail"].startswith("705 claimed against 441 supplied")
    assert len(line["checks"]) == 8  # every check ran
    assert line["recommendation"]["action"] == "approve_part" and line["recommendation"]["qty"] == 441


def test_status_of_another_stockists_claim_is_not_disclosed(monkeypatch):
    """EML-023's claim number, asked from a different stockist's mailbox."""
    monkeypatch.setattr(nodes, "get_llm", no_model)
    row = {**email_row("EML-023"), "stockist_code_by_mailbox_rule": "STK0001"}
    facts = run("email", row)["status_facts"]
    assert facts == ["CLM-2608-02444: no such claim on this stockist's account"]


# --- live: the real model against the agreed forms --------------------------------------
def _comparable(form: dict) -> dict:
    lines = [((c.get("batch_no") or "").strip().upper() or None, c.get("qty_claimed"),
              tools.norm_invoice(c["invoice_ref"]) if c.get("invoice_ref") else None,
              nodes.parse_expiry_text(c.get("expiry_text")))
             for c in form.get("claims", [])] if form.get("kind") == "claim" else []
    return {"kind": form.get("kind"), "lines": lines, "refs": sorted(form.get("claim_refs", []))}


@pytest.mark.live
@pytest.mark.skipif(not os.getenv("OPENROUTER_API_KEY"), reason="needs OPENROUTER_API_KEY")
@pytest.mark.parametrize("case", CASES["emails"], ids=[c["id"] for c in CASES["emails"]])
def test_live_extraction_matches_agreed_form(case):
    form, _, error = nodes.extract_email(email_row(case["id"]))
    assert error is None
    got = nodes.clean_form(form).model_dump()  # what the graph uses
    assert _comparable(got) == _comparable(case["form"]), case["why"]


def test_clean_form_drops_empty_lines_and_model_set_expiry_types():
    form = ExtractedEmail(kind="claim", claims=[
        {"claim_type": "Expired"}, {"batch_no": "K2430146", "qty_claimed": 5, "claim_type": "Expired"},
        {"batch_no": "M2400719", "qty_claimed": 3, "claim_type": "Short supply"}])
    lines = nodes.clean_form(form).claims
    assert [(ln.batch_no, ln.claim_type) for ln in lines] == [("K2430146", None), ("M2400719", "Short supply")]
