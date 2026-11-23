# 0011. React (Vite) frontend built into `public/`

- Status: Accepted (supersedes the starter's plain HTML/JS page)
- Date: 2026-11-20

## Context
The page grew: per-line claim cards, check tables, status facts, draft replies, a decision bar,
watch views with data rows and sources, and results that should survive switching tabs. The
starter rule was plain HTML, CSS and JavaScript in `public/`. The product owner asked for React.

## Decision
- React 18 with Vite in `frontend/`. `npm run build` writes `public/`, which FastAPI serves locally
  and Vercel serves from its CDN, so the backend did not change.
- The built `public/` is committed, so Vercel needs no Node build step. `public/` is never edited
  by hand.
- `npm run dev` serves the page on :5173 and proxies `/api` to uvicorn on :8000.
- Server text is rendered as text (React's default). `dangerouslySetInnerHTML` is not used:
  email text is data (0006).
- Plain CSS with light and dark tokens; no UI framework.

## Alternatives considered
- **React from a CDN without a build.** Rejected: no JSX tooling, slower page, pinned script tags.
- **Build on Vercel.** Possible later; mixing a Node build with the Python function adds a moving
  part for little gain now.

## Consequences
- A frontend change needs `npm run build` before commit, or the deployed page is stale.
- Bundle: about 49 KB gzipped.
- 20 Nov 2026: the claims desk is one inbox, not two pickers. Mailbox emails and pending register
  claims are two sources of the same work, so they sit in one list (filter All / Mailbox /
  Register, search, arrow keys). Opening an item checks it; results are cached. The reading pane
  shows the outcome summary, one card per line (recommendation, failing checks with clauses, all
  checks folded), the draft to the stockist with Copy, and the original email or register entry
  beside it. The decision bar stays in reach, remembers the decider's name in this browser, marks
  the item in the list and moves to the next. On a phone the list and the case are separate
  screens.
- 21 Nov 2026: every tab is now a work screen (0014, 0015, 0016); the Weekly digest is the first tab and
  links into the others. The "Run" panel is gone.
