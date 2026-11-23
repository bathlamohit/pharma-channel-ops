"""cite_and_format: the last node before anything reaches the page.

Any number in model-written text that is not in the cited facts is stripped and shown
as "data incomplete". Text built by code from templates (explanations, replies, letters
since ADR 0012) is not model-written and is not filtered; a node that lets a model write
text lists the key in state["model_text"].
"""
import re

from agent.state import SankalpState

NUMBER = re.compile(r"(?<![A-Za-z])\d[\d,]*(?:\.\d+)?")
PLACEHOLDER = "[data incomplete]"


def _numbers(text: str) -> set[str]:
    return {m.replace(",", "") for m in NUMBER.findall(text or "")}


def allowed_numbers(state: SankalpState) -> set[str]:
    """Numbers that came from code: check details, the claim fields, watch summaries."""
    sources = []
    for i, line in enumerate(state.get("lines", []), 1):
        sources += [str(i)] + [f"{r['detail']} {r['clause']}" for r in line["checks"].values()]
        sources += [str(v) for v in line["claim"].values()] + line["errors"]
    sources += state.get("status_facts", [])
    sources += [v["summary"] for v in state.get("watch", {}).values()]
    sources += [str(state.get("raw_input", {}))]
    return set().union(*(_numbers(s) for s in sources)) if sources else set()


def strip_uncited(text: str, allowed: set[str]) -> tuple[str, int]:
    stripped = 0

    def sub(m: re.Match) -> str:
        nonlocal stripped
        if m.group(0).replace(",", "") in allowed:
            return m.group(0)
        stripped += 1
        return PLACEHOLDER

    return NUMBER.sub(sub, text or ""), stripped


def cite_and_format(state: SankalpState) -> dict:
    allowed = allowed_numbers(state)
    out, errors = {}, []
    for key in state.get("model_text") or []:
        if state.get(key):
            out[key], n = strip_uncited(state[key], allowed)
            if n:
                errors.append(f"{n} uncited number(s) removed from {key}")
    return {**out, "errors": errors}
