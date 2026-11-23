# Architecture Decision Records

Each record states one decision: the context, what we chose, what we rejected and why, and what
follows from it. A record is never edited to change its decision; a new record supersedes it.

| # | Decision | Status |
|---|---|---|
| [0001](0001-one-langgraph-workflow-code-first.md) | One LangGraph workflow; code applies rules, the model only reads and words | Accepted |
| [0002](0002-recommend-dont-decide.md) | The graph recommends; a person decides in a second request; nothing auto-approved | Accepted |
| [0003](0003-seven-claim-checks-in-code.md) | Seven claim checks as pure functions, thresholds in one policy file | Accepted |
| [0004](0004-every-number-cited.md) | Every number carries its file, rows and snapshot; a guard strips uncited numbers | Accepted |
| [0005](0005-clean-once-at-build-time.md) | Clean the extracts once at build time, log every fix, keep original line numbers | Accepted |
| [0006](0006-email-text-is-data.md) | Email text is data: fixed form, identity from the mailbox rule, rules enforced in code | Accepted |
| [0007](0007-one-claim-subgraph-per-line.md) | Each claim line runs through its own claim subgraph | Accepted |
| [0008](0008-tests-reproduce-verified-figures.md) | Tests reproduce the verified figures; an agreed check set guards the claim path | Accepted |
| [0009](0009-metric-definitions.md) | Metric definitions for the watch views | Accepted; cover, unfilled and donor parts superseded by 0017 |
| [0010](0010-fastapi-on-vercel-stateless.md) | FastAPI on Vercel, stateless, with pre-cleaned tables committed | Accepted; audit store open |
| [0011](0011-react-frontend-built-to-public.md) | React (Vite) frontend built into `public/` | Accepted |
| [0012](0012-deterministic-claim-handling.md) | Claims handled by policy code; the model is only a fallback reader | Accepted |
| [0013](0013-new-claims-file-store.md) | New claims: intake, claim numbers and status in an append-only file | Accepted (local; hosted store open) |
| [0014](0014-expiry-and-dispatch-work-screen.md) | Expiry and dispatch as a work screen: block, consent, CDC return, pick order | Accepted |
| [0015](0015-allocation-work-screen.md) | Allocation as a work screen: refill, too much, moves via the CDC, schemes | Superseded in part by 0017 |
| [0016](0016-weekly-digest-by-owner.md) | Weekly digest: one page per owner, linked to the work screens | Accepted |
| [0017](0017-demand-from-invoices.md) | Demand from invoices, not the SAP stock report; allocation on current shares | Accepted (share change awaits client) |

Source documents: [Final Plan](https://claude.ai/artifact/4yZwzq4wwjs6TKyuu1dovi),
[Workflow v2](https://claude.ai/artifact/DnfKWnGhgXmSAy8kVxcMjg), the course starter, and the
discovery note's evidence log.
