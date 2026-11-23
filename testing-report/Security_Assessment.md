# Security assessment

**Scope:**
- API: 23 endpoints.
- React page.
- Configuration: `.env`, `.gitignore`, `vercel.json`.
- The local file stores.

**Method:**
- Automated tests: `automated_tests/test_05_security.py`, `test_06_concurrency.py`.
- Code review.

This is not a penetration test of a deployed environment. The tests ran locally against synthetic
data.

## Summary

| Area | Result |
|---|---|
| Path traversal and file exposure | **Pass.** The source viewer serves only 7 named tables (8 traversal strings refused). `.env`, data, logs and source are not served. |
| Secrets | **Pass.** No key or `.env` value in the built page. `.env` and the stores are git-ignored. The key is read only on the server. |
| Script injection (XSS) | **Pass.** React renders all text as text; no `dangerouslySetInnerHTML` or `innerHTML`. Markup in names and emails is stored as data and shown as text. |
| Prompt injection | **Pass.** An instruction inside an email (EML-017, and a synthetic case) changes nothing: all 8 checks run. The sender comes from the mailbox account, never from the text. |
| SQL / shell injection | **Pass (not applicable).** No database or shell. Such strings are treated as plain text (404). |
| Information disclosure | **Pass.** Error responses carry no stack trace, path or file name. Another stockist's claim status is never disclosed. |
| Input validation | **Pass.** Types, lengths, ranges, dates and enums are enforced; text is trimmed before its length is checked (31 cases). |
| Request size | **Pass.** Bodies over 64 KB are refused (413); the source viewer refuses 100,000 rows. |
| Security headers | **Fixed (D-01).** There were none. Now `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, and a Content-Security-Policy (`default-src 'self'`, `frame-ancestors 'none'`), set by the app and by `vercel.json` for CDN-served files. |
| Integrity under concurrency | **Fixed (D-02, D-03).** Simultaneous approvals were all recorded (double-credit risk); a read during registration caused a 500. Now one locked write per claim registration, one lock around each decision check and write, and shared-lock reads. |
| CORS | **Pass.** No CORS headers, so other sites' scripts cannot call the API from a browser. |
| **Authentication** | **Open, High (O-01).** No sign-in. Anyone who can reach the URL can record decisions and steps. Recorded as expected failure TC-SEC-010. |
| **Authorisation / roles** | **Open, High (O-02).** No roles. Any user can record "Return approved", which belongs to the Head of Supply Chain (CF Sch 2 2.5), or approve a claim. Expected failure TC-SEC-011. |
| Rate limiting | **Open, Low (O-04).** None in the app; Vercel's platform limits apply when deployed. Expected failure TC-SEC-013. |
| Audit trail durability | **Open, High for production (O-03).** Decisions and steps are kept in local files; on Vercel they do not persist. |
| Personal data | **Note.** The stores keep stockist names and email text as received. They are git-ignored, but they sit on disk unencrypted; a hosted store should encrypt at rest and set retention (the C&F agreement asks for 5 years, Sch 2 2.8). |
| Dependencies | **Not assessed.** No vulnerability scanner (pip-audit, npm audit) was run in this session. Recommended before deployment. |

## Recommendations before any real use

1. **Sign-in.** Vercel password protection now, company SSO next. Take the decider's name from the
   session, not a text box (O-01).
2. **Roles.** Map each step to a role: CFA (verify, block), Regional Distribution Manager (request
   a return), Head of Supply Chain (approve a return), claims desk (decide), Commercial Finance
   (credit note). Enforce them on the server (O-02).
3. **Hosted store.** Use a hosted database for claims, steps and decisions, encrypted at rest with
   retention set (O-03).
4. **Dependency scans.** Run `pip-audit` and `npm audit` in CI.
