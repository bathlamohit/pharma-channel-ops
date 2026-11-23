# 0001. One LangGraph workflow; code applies rules, the model only reads and words

- Status: Accepted; amended by 0012 (the model is only a fallback email reader)
- Date: 2026-11-16

## Context
The pilot serves three users with three jobs: the claims desk (Commercial Finance), the expiry
and dispatch watch (Supply Chain) and the allocation view (Demand Planning and RSMs). Every
claim decision is money, so Finance and Audit need answers that are repeatable and explainable.
The team's architecture note proposed a model-based router for intent and a tool-calling loop.

## Decision
- One LangGraph `StateGraph` (`agent/graph.py`) with three entry points chosen by the tab the user
  pressed: `email`, `register` and `watch`. No model decides the route.
- Plain Python does every lookup, rule, calculation and route.
- The model is called in exactly three places: reading an email into a fixed form
  (`extract_claim`), drafting a reply (`draft_reply`) and wording the reason for each line
  (`explain`).
- One file knows the model provider: `agent/llm.py` (OpenRouter, `MODEL` env var, default
  `openai/gpt-4o-mini`).

## Alternatives considered
- **Model router plus tool loop (starter / team note).** Rejected: three buttons already state the
  intent, so a router adds cost and a way to be wrong; a tool loop lets the model choose which
  facts to fetch, which a reviewer cannot audit.
- **Model applies the policy.** Rejected: rules such as "90 days after expiry" must give the same
  answer every time and be testable without a key.

## Consequences
- A claim costs 2 model calls (email) or 1 (register); a watch view costs 0. About 1,000-1,500
  tokens and 3-6 s per email with gpt-4o-mini.
- The whole graph runs offline with a fake model, so `pytest -q` needs no key.
- Changing provider or model is a one-file change.
