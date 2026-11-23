# 0007. Each claim line runs through its own claim subgraph

- Status: Accepted
- Date: 2026-11-20

## Context
Emails list several claims (EML-002 has three). The plan requires each line to be checked as its
own claim. EML-013 repeats the same line twice in one email. The first skeleton checked only the
first line, and the seven parallel checks wrote into one shared `checks` key.

## Decision
- A compiled claim subgraph (`build_claim_graph`): resolve_records -> 7 checks in parallel ->
  decide_route, or needs_person when the stockist or batch is missing.
- `check_lines` runs it once per line in order. Earlier lines of the same email are passed in as
  prior claims, so a repeated line is caught by the duplicate check.
- Each line gets its own route, checks and errors. The overall route is `reject` or `clean` only
  when every line agrees; anything mixed goes to a person.
- A register claim is a one-line case of the same path.
- `explain` is one model call for all lines, returning a reason per line number.

## Alternatives considered
- **LangGraph `Send` per line into the top graph.** Rejected: check results from different lines
  would collide in one state key and need line-scoped reducers.
- **One graph run per line from the API.** Rejected: would read the email once per line.

## Consequences
- The page shows one card per line. Line ids are `EML-013#1`, `EML-013#2`.
- Lines run one after another; a long email is linear in its lines.
