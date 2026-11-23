# Testing report: how to reproduce

Everything in this folder was produced by running the commands below on 21 Nov 2026. The data is
the pilot's extract in `data/` (stock and register to 30 Sep 2026) plus synthetic test data.

**Nothing here writes to your real files.** Every test runs against temporary stores (claims,
stock actions, audit log), and the model key is removed, so no test calls the model or costs
money.

## Contents

| File / folder | What it is |
|---|---|
| `QA_Executive_Report.md` | Overall assessment: inventory, strategy, results, defects, production readiness |
| `Test_Cases.xlsx` | All 200 QA test cases and 185 unit/regression tests, with results; summary by module (formulas) |
| `Defect_Register.xlsx` | 25 entries: 8 found and fixed in this assessment (D-), 8 fixed earlier the same day (B), 9 open items and decisions (O-), plus the summary |
| `Backtesting_Report.md` | Independent recalculation, claim-rule back-test, and a time-ordered stock-forecast backtest |
| `API_Test_Report.md` | Every endpoint: contract, errors, validation, duplicates, concurrency |
| `Security_Assessment.md` | Security findings and fixes |
| `Performance_Report.md` | Latency, load and scalability, before and after the fix |
| `test_data/` | `generate.py` (seed 20261121) and the generated datasets |
| `automated_tests/` | The pytest + Playwright suite (`conftest.py` holds the fixtures) |
| `evidence/` | Results, API request/response log, JUnit XML, performance and backtest JSON, screenshots |
| `build_registers.py` | Builds the two Excel files from `evidence/` |
| `requirements-test.txt` | Extra test packages (Playwright, openpyxl) |

## Setup (once)

From the project root:

```bash
uv pip install --python .venv/bin/python -r testing-report/requirements-test.txt
```

```bash
.venv/bin/python -m playwright install chromium
```

## Run everything

```bash
.venv/bin/python testing-report/test_data/generate.py
```

```bash
.venv/bin/python -m pytest testing-report/automated_tests -p no:cacheprovider -q -rxX --junitxml=testing-report/evidence/junit_qa.xml
```

```bash
.venv/bin/python -m pytest -q --junitxml=testing-report/evidence/junit_unit.xml
```

```bash
.venv/bin/python scripts/qa_check.py
```

```bash
.venv/bin/python scripts/qa_consistency.py
```

```bash
.venv/bin/python -m agent.backtest
```

```bash
.venv/bin/python testing-report/build_registers.py
```

- The QA suite takes about 3 minutes. Most of that is the 1,000-claim load test and the browser
  tests.
- `-rxX` lists the 3 expected failures: known gaps that need a decision (sign-in, roles, rate
  limiting).
- Run a single area with `-k`, e.g. `-k e2e`, or by file, e.g. `automated_tests/test_06_concurrency.py`.

## Test data (`test_data/`)

| File | Records | Covers |
|---|---|---|
| `intake_form_cases.json` | 19 | Claims dated on the policy boundaries (90 vs 91 days after expiry, 90 vs 91 before, 7 vs 8 days after invoice), quantity equal to / one over supply, 0, negative, fractional, 10^12, unknown type, missing batch, no invoice, lower-case and odd formats, a duplicate line |
| `intake_email_cases.json` | 12 | Valid email, prompt injection, unknown sender, status question, not a claim, unreadable, HTML in the name, blank, over 20,000 characters, future date, bad date format, unknown account |
| `volume_emails.json` | 1,000 | Five realistic email layouts (plain, table, Hinglish, short, boxes × strips) for the load test |

Combinations of stockist, batch and invoice are real rows from the extract, chosen so the checks
have records to find. Quantities, dates and wording are synthetic. Expected outcomes come from
the policy text, not the application's code. Re-running `generate.py` gives the same files.

## Notes

- **Spreadsheet formulas.** The summary sheets use COUNTIFS formulas and are set to recalculate
  when opened. LibreOffice was not available to pre-compute them here; the same counts were
  checked in Python (`build_registers.py` prints them).
- **Live model tests.** The 30 tests in `tests/` marked `live` were not run. The model is now only
  a fallback reader, and these tests cost money: `pytest -q -m live` with a key.
