# 0004. Every number carries its file, rows and snapshot; a guard strips uncited numbers

- Status: Accepted
- Date: 2026-11-16

## Context
The accuracy bar is that no number reaches a Finance user unless it can be traced to the data.
Models invent plausible numbers.

## Decision
- Tools (`agent/tools.py`) return `{found, rows, citation}`; a citation is
  `{file, rows: [original line numbers], snapshot}`. "Not found" is an answer, never a guess.
- Checks and watch views carry the citations of the rows they used.
- `cite_and_format` (`agent/guard.py`) is the last node before output. Any number in model-written
  text (explanation, reply) that does not appear in the code-built facts, the claim fields, the
  status facts, the policy clauses or the email itself becomes `[data incomplete]`, and the run
  records how many were removed.
- The route label on each line is written by code; the model writes only the reason.

## Alternatives considered
- **Trust the prompt ("do not invent numbers").** Rejected: the guard costs nothing and is tested.
- **Let the model state the route.** Rejected after a live run: it called a clean line
  "to_person" and a failing claim "valid".

## Consequences
- The guard matches digits, not meaning: it cannot catch a wrong word. That is why routes and
  labels come from code.
- Every check-set case injects an invented number and asserts it never reaches the output.
- "Show rows" on any source opens the cited rows as cleaned (`POST /api/source`), with each
  cell the build changed marked and its original value listed, and lines dropped as exact
  duplicates named. Fix-log entries where nothing changed are left out.
