"""Build Test_Cases.xlsx and Defect_Register.xlsx from the evidence of the last run.

    .venv/bin/python testing-report/build_registers.py

Reads evidence/results.jsonl (QA suite) and evidence/junit_unit.xml (unit suite). Summary sheets
use COUNTIFS formulas over the detail sheets; the workbook is set to recalculate on open.
"""
import json
import re
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.workbook.properties import CalcProperties

HERE = Path(__file__).resolve().parent
EV = HERE / "evidence"
FONT, BOLD = Font(name="Arial", size=10), Font(name="Arial", size=10, bold=True)
HEAD_FILL = PatternFill("solid", fgColor="1F2937")
HEAD_FONT = Font(name="Arial", size=10, bold=True, color="FFFFFF")
FILL = {"passed": "E7F6EE", "failed": "FDECEA", "xfailed": "FDF1E3", "skipped": "EEF0F6",
        "Fixed": "E7F6EE", "Open": "FDECEA", "Open (decision)": "FDF1E3", "Accepted risk": "EEF0F6"}
THIN = Border(bottom=Side(style="thin", color="E4E6EF"))
MODULE = {"test_01": "API contract", "test_02": "Claims desk", "test_03": "Expiry, Allocation, Digest",
          "test_04": "Input validation", "test_05": "Security", "test_06": "Concurrency", "test_07": "Performance",
          "test_08": "Backtesting", "test_09": "UI end-to-end"}


def table(ws, headers, rows, widths):
    ws.append(headers)
    for c in ws[1]:
        c.font, c.fill, c.alignment = HEAD_FONT, HEAD_FILL, Alignment(vertical="center", wrap_text=True)
    for r in rows:
        ws.append(r)
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.font, c.border = FONT, THIN
            c.alignment = Alignment(vertical="top", wrap_text=True)
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions


def colour(ws, col_letter):
    for c in ws[col_letter][1:]:
        if c.value in FILL:
            c.fill = PatternFill("solid", fgColor=FILL[c.value])


def qa_rows():
    out, seen = [], Counter()
    for line in (EV / "results.jsonl").read_text().splitlines():
        r = json.loads(line)
        m = re.search(r"\[(.+)\]$", r["nodeid"])
        param = m.group(1) if m else None
        base = r["tc_id"].rstrip("x").rstrip("-") if r["tc_id"].endswith("x") else r["tc_id"]
        tc = param if param and param.startswith("TC-") else (f"{base}-{param}" if param else base)
        seen[tc] += 1
        if seen[tc] > 1:
            tc = f"{tc}.{seen[tc]}"
        mod = MODULE.get(Path(r["nodeid"].split("::")[0]).name[:7], "Other")
        out.append([tc, mod, r["type"], r["requirement"], r["description"], r["nodeid"], r["outcome"], r["seconds"],
                    (r["message"] or "")[:300]])
    return out


def unit_rows():
    root = ET.parse(EV / "junit_unit.xml").getroot()
    out = []
    for tcase in root.iter("testcase"):
        outcome = "failed" if tcase.find("failure") is not None or tcase.find("error") is not None else \
            "skipped" if tcase.find("skipped") is not None else "passed"
        out.append([tcase.get("classname"), tcase.get("name"), outcome, float(tcase.get("time", 0))])
    return out


def build_test_cases():
    wb = Workbook()
    wb.calculation = CalcProperties(fullCalcOnLoad=True)
    s = wb.active
    s.title = "Summary"
    qa, unit = qa_rows(), unit_rows()
    d = wb.create_sheet("QA test cases")
    table(d, ["Test case ID", "Module", "Type", "Requirement / source", "Description", "Automated test", "Result",
              "Seconds", "Notes (failure or known-gap reason)"], qa, [16, 22, 22, 26, 60, 60, 10, 9, 60])
    colour(d, "G")
    u = wb.create_sheet("Unit and regression")
    table(u, ["Test module", "Test", "Result", "Seconds"], unit, [34, 70, 10, 9])
    colour(u, "C")
    n = len(qa) + 1
    s["A1"] = "Project Sankalp: test case summary (from the last full run)"
    s["A1"].font = Font(name="Arial", size=13, bold=True)
    s["A2"] = "Formulas count the rows of the detail sheets. Result values: passed, failed, xfailed (known gap, open decision), skipped."
    s["A2"].font = FONT
    heads = ["Module", "Total", "Passed", "Failed", "Known gap (xfail)", "Skipped", "Pass % of executed"]
    for i, h in enumerate(heads, 1):
        c = s.cell(row=4, column=i, value=h)
        c.font, c.fill = HEAD_FONT, HEAD_FILL
    mods = list(dict.fromkeys(r[1] for r in qa))
    rng_m, rng_r = f"'QA test cases'!$B$2:$B${n}", f"'QA test cases'!$G$2:$G${n}"
    row = 5
    for m in mods:
        s.cell(row=row, column=1, value=m)
        s.cell(row=row, column=2, value=f'=COUNTIFS({rng_m},A{row})')
        for col, res in ((3, "passed"), (4, "failed"), (5, "xfailed"), (6, "skipped")):
            s.cell(row=row, column=col, value=f'=COUNTIFS({rng_m},A{row},{rng_r},"{res}")')
        s.cell(row=row, column=7, value=f'=IFERROR(C{row}/(C{row}+D{row}+E{row}),0)').number_format = "0.0%"
        row += 1
    s.cell(row=row, column=1, value="QA suite total").font = BOLD
    for col in range(2, 7):
        L = get_column_letter(col)
        s.cell(row=row, column=col, value=f"=SUM({L}5:{L}{row - 1})").font = BOLD
    s.cell(row=row, column=7, value=f"=IFERROR(C{row}/(C{row}+D{row}+E{row}),0)").number_format = "0.0%"
    qa_total_row = row
    row += 1
    un = len(unit) + 1
    s.cell(row=row, column=1, value="Unit and regression suite (tests/)")
    s.cell(row=row, column=2, value=f"=COUNTA('Unit and regression'!$C$2:$C${un})")
    s.cell(row=row, column=3, value=f"=COUNTIFS('Unit and regression'!$C$2:$C${un},\"passed\")")
    s.cell(row=row, column=4, value=f"=COUNTIFS('Unit and regression'!$C$2:$C${un},\"failed\")")
    s.cell(row=row, column=5, value=0)
    s.cell(row=row, column=6, value=f"=COUNTIFS('Unit and regression'!$C$2:$C${un},\"skipped\")")
    s.cell(row=row, column=7, value=f"=IFERROR(C{row}/(C{row}+D{row}+E{row}),0)").number_format = "0.0%"
    row += 1
    s.cell(row=row, column=1, value="All automated tests").font = BOLD
    for col in range(2, 7):
        L = get_column_letter(col)
        s.cell(row=row, column=col, value=f"={L}{qa_total_row}+{L}{qa_total_row + 1}").font = BOLD
    s.cell(row=row, column=7, value=f"=IFERROR(C{row}/(C{row}+D{row}+E{row}),0)").number_format = "0.0%"
    s.cell(row=row + 2, column=1, value="Not automated here: live model tests (30, opt-in, cost money; the model is only a fallback reader). "
                                        "Independent figure check (30) and consistency checks (210) are separate scripts; see QA_Executive_Report.md.").font = FONT
    for r in s.iter_rows(min_row=5, max_row=row):
        for c in r:
            if not c.font.bold:
                c.font = FONT
    for i, w in enumerate([34, 9, 9, 9, 16, 9, 18], 1):
        s.column_dimensions[get_column_letter(i)].width = w
    wb.save(HERE / "Test_Cases.xlsx")
    # Python cross-check of what the formulas will show
    by = Counter((r[1], r[6]) for r in qa)
    return {"qa": len(qa), "qa_passed": sum(v for (m, o), v in by.items() if o == "passed"),
            "qa_failed": sum(v for (m, o), v in by.items() if o == "failed"),
            "qa_xfailed": sum(v for (m, o), v in by.items() if o == "xfailed"),
            "unit": len(unit), "unit_passed": sum(1 for r in unit if r[2] == "passed"),
            "by_module": {m: sum(v for (mm, o), v in by.items() if mm == m) for m in mods}}


DEFECTS = [
    # id, title, severity, priority, module, found by, reproduce, root cause, fix, status, re-test, regression tests
    ("D-01", "Responses carry no security headers (nosniff, frame protection, CSP)", "Medium", "P2", "Security / all pages",
     "TC-SEC-012", "GET / and check headers: no X-Content-Type-Options, X-Frame-Options or Content-Security-Policy.",
     "No header middleware; Vercel serves public/ without a vercel.json.",
     "Middleware in app.py adds nosniff, X-Frame-Options DENY, Referrer-Policy, CSP with frame-ancestors 'none'; vercel.json sets the same for CDN files.",
     "Fixed", "Passed", "TC-SEC-012; tests/test_qa_fixes.py::test_d01"),
    ("D-02", "Simultaneous identical approvals are all recorded (double credit under concurrency)", "High", "P1", "Claims desk / decisions",
     "TC-CON-002", "Check CLM-2606-02056, then send 10 identical approvals at once: 4 recorded.",
     "'Already decided?' read and the write were not atomic; requests ran in parallel threads.",
     "audit.decision_lock(): an exclusive file lock around the check and the write in POST /api/decision.",
     "Fixed", "Passed (3 repeat runs)", "TC-CON-002"),
    ("D-03", "Server error (500) when a claim is read while another is being registered", "High", "P1", "New claims store",
     "TC-CON-001", "Post 40 claim forms with 8 threads: KeyError 'status' in store.claims(), connection reset.",
     "A registration was written as three separate appends; an unlocked reader could see 'registered' without 'status'.",
     "The three events are written in one locked write; reads take a shared lock; replay skips a claim without a status.",
     "Fixed", "Passed (3 repeat runs)", "TC-CON-001; tests/test_qa_fixes.py::test_d03"),
    ("D-04", "Read screens slow under concurrent use; claims store replayed on every check", "Medium", "P2", "Performance",
     "TC-PRF-003, TC-PRF-004", "10 users on the read screens: p95 10.5 s, max 15.5 s. With 1,000 new claims a check took 74 ms (21 ms empty).",
     "Digest, stock and allocation plans recomputed from the full extract on every request (0.1-0.8 s each, CPU-bound); store replayed in full per call.",
     "Results that depend only on the extract are cached per process and returned as copies; the store is replayed once per file version.",
     "Fixed", "Passed: p95 0.51 s, max 0.77 s, 25.9 req/s; check 21 ms at 1,000 claims", "TC-PRF-001..004; all functional suites"),
    ("D-05", "'Mark verified' refuses a person who has typed their name", "Medium", "P2", "Claims desk / new claim status",
     "TC-E2E-005", "Open a new claim, type a name in the decision bar, click 'Mark verified at CFA': 'Enter your name in the decision bar first.'",
     "The status panel reads the name from browser storage; the decision bar saved it only after a decision.",
     "The decision bar saves the name as it is typed.", "Fixed", "Passed", "TC-E2E-005"),
    ("D-06", "Clicking a just-logged claim number does nothing while the list refreshes", "Low", "P3", "Claims desk / new claim",
     "TC-E2E-005 (full run)", "With ~1,000 stored claims, log a new email and click the claim number under 'Logged as' at once: nothing opens.",
     "The click looked up the claim in a list still being refreshed and silently found nothing.",
     "If the claim is not in the list, refresh it first, then open; otherwise show a message.", "Fixed", "Passed", "TC-E2E-005"),
    ("D-07", "New-claim date defaults to the UTC date (a day behind in India before 05:30)", "Low", "P3", "Claims desk / new claim",
     "Screenshot review, TC-E2E-011", "At 02:00 IST the form shows yesterday's date.",
     "toISOString() returns the UTC date.", "Local date built from the browser's clock.", "Fixed", "Passed", "TC-E2E-011"),
    ("D-08", "A greeting is shown as the product ('Dear sir')", "Low", "P3", "Email reader",
     "Screenshot review", "Paste 'Dear sir, batch F2420525, 12 strips': the line card is titled 'Dear sir'.",
     "The reader took the text before 'batch' as the product, greeting included.",
     "Greetings (dear sir/madam/team, hi, hello, namaste, sir) are stripped from the product text.", "Fixed", "Passed",
     "tests/test_reader.py::test_greeting_is_not_a_product; check set unchanged"),
    # Earlier the same day (docs/qa-report-2026-11-21.md), fixed and covered by tests/test_qa_fixes.py
    ("B1", "A claim could be approved more than once", "High", "P1", "Decisions", "QA probe", "Approve twice, or re-check then approve.",
     "No one-decision-per-claim rule.", "One decision per claim or email across audit ids; change needs a reason.", "Fixed", "Passed", "tests/test_qa_fixes.py::test_b1_*"),
    ("B2", "Decision accepted for an unknown audit id", "High", "P1", "Decisions", "QA probe", "POST /api/decision with a made-up id.",
     "Audit id not checked.", "404 where the server keeps its log.", "Fixed", "Passed", "test_b2"),
    ("B3", "Step accepted for an unknown CFA, product or batch", "Medium", "P2", "Stock / allocation steps", "QA probe", "cnf_code XX-999 accepted.",
     "No validation against the plan.", "Validated against snapshot, SKU master and held batches.", "Fixed", "Passed", "test_b3"),
    ("B4", "Same step recorded twice", "Medium", "P2", "Stock / allocation steps", "QA probe", "Post the same step twice.",
     "No uniqueness rule.", "Once per CFA, product, batch and note; two recurring steps allowed.", "Fixed", "Passed", "test_b4"),
    ("B5", "Names of only spaces stored as blank", "Medium", "P2", "All write endpoints", "QA probe", "by = '    '.",
     "Length checked before trimming.", "Trim before validation; stores refuse blank names.", "Fixed", "Passed", "test_b5"),
    ("B6", "Blank email drafted a 'forwarded' reply", "Low", "P3", "New claims", "QA probe", "body = '   '.", "Same as B5.", "422.", "Fixed", "Passed", "test_b6"),
    ("B7", "limit=-1 silently dropped one claim", "Low", "P3", "API", "QA probe", "GET /api/claims?limit=-1 → 359.", "pandas head(-1).", "limit 1..1000.", "Fixed", "Passed", "test_b7"),
    ("B8", "Negative offset returned rows from the end", "Low", "P3", "Source viewer", "QA probe", "offset=-5.", "No bound.", "offset ≥ 0.", "Fixed", "Passed", "test_b8"),
    # Open items: not code defects that can be fixed safely here, or decisions for the client
    ("O-01", "No sign-in: anyone with the URL can act", "High", "P1", "Security", "TC-SEC-010 (xfail)", "Call any write endpoint without credentials.",
     "Not built; open decision (identity provider).", "Vercel password protection now; company SSO later; decider from the session.", "Open (decision)", "Known gap", "TC-SEC-010"),
    ("O-02", "No roles: anyone can approve, or record 'Return approved' meant for the Head of Supply Chain", "High", "P1", "Security",
     "TC-SEC-011 (xfail)", "Record 'Return approved' as any name.", "No role model.", "Roles from sign-in; enforce who may take each step (CF Sch 2 2.5, CO-POL-014 4.3).", "Open (decision)", "Known gap", "TC-SEC-011"),
    ("O-03", "Stores do not persist on Vercel (claims, steps, audit log)", "High", "P1", "Deployment", "ADR 0010, 0013", "Deploy; restart; data gone.",
     "Read-only disk on Vercel; file stores by design for the pilot.", "Hosted Postgres behind store.py / stock_log.py / audit.py.", "Open (decision)", "Known gap", "-"),
    ("O-04", "No rate limiting", "Low", "P3", "Security", "TC-SEC-013 (xfail)", "300 rapid requests, none throttled.", "Not built.", "Platform limits or middleware once signed in.", "Open (decision)", "Known gap", "TC-SEC-013"),
    ("O-05", "Stock forecast weaker than a simple baseline at 2-3 months; 'will not sell in time' precision 0.43-0.74", "Medium", "P2",
     "Expiry & dispatch forecast", "TC-BKT-003, TC-BKT-004", "See Backtesting_Report.md.",
     "Model assumes oldest-first picking at average outward; Kolkata picks out of order (misses), others sell older stock faster (over-flags).",
     "Business decision: label as 'likely', blend with recent batch sell-through, or calibrate per CFA; re-run the backtest.", "Open (decision)", "Measured", "TC-BKT-003/004"),
    ("O-06", "Data extract is static (to 30 Sep 2026)", "Medium", "P2", "Data", "ADR 0013", "A genuine claim on stock invoiced after 30 Sep fails 'never supplied'.",
     "No SAP feed in the pilot.", "Daily extract refresh of data/clean/.", "Open (decision)", "Known gap", "-"),
    ("O-07", "API default 'received today' uses the server date (UTC on Vercel)", "Low", "P3", "New claims API", "Code review",
     "POST /api/intake/email without received_date between 00:00 and 05:30 IST.", "date.today() on the server.",
     "Use Asia/Kolkata for the default; the page always sends a local date (D-07).", "Open", "Not fixed (needs a time-zone decision)", "-"),
    ("O-08", "Listing new claims takes ~0.3 s at 1,000 claims (full payload)", "Low", "P3", "Performance", "TC-PRF-004",
     "GET /api/intake with 1,000 claims.", "Every claim is returned with its checks.", "Paginate or drop check detail from the list.", "Accepted risk", "Measured", "TC-PRF-004"),
    ("O-09", "Plan's '69% of claims over 30 days' cannot be reproduced", "Low", "P3", "Claims ageing", "ADR 0009", "-",
     "Population and as-of date not stated in the plan.", "Confirm with the client; app shows 129 of 360 pending over 30 days at the snapshot.", "Open (decision)", "-", "-"),
]


def build_defects():
    wb = Workbook()
    wb.calculation = CalcProperties(fullCalcOnLoad=True)
    s = wb.active
    s.title = "Summary"
    d = wb.create_sheet("Defects")
    heads = ["ID", "Title", "Severity", "Priority", "Module", "Found by", "Steps to reproduce", "Root cause", "Fix / proposal",
             "Status", "Re-test", "Regression tests"]
    table(d, heads, [list(x) for x in DEFECTS], [7, 46, 9, 8, 22, 18, 46, 46, 50, 15, 22, 30])
    colour(d, "J")
    n = len(DEFECTS) + 1
    s["A1"] = "Project Sankalp: defect register summary"
    s["A1"].font = Font(name="Arial", size=13, bold=True)
    s["A2"] = "D-: found and fixed in this assessment. B-: found and fixed earlier the same day. O-: open items and decisions for the client."
    s["A2"].font = FONT
    statuses = ["Fixed", "Open", "Open (decision)", "Accepted risk"]
    for i, h in enumerate(["Severity", *statuses, "Total"], 1):
        c = s.cell(row=4, column=i, value=h)
        c.font, c.fill = HEAD_FONT, HEAD_FILL
    for r, sev in enumerate(["High", "Medium", "Low"], 5):
        s.cell(row=r, column=1, value=sev).font = FONT
        for j, st in enumerate(statuses, 2):
            s.cell(row=r, column=j, value=f'=COUNTIFS(Defects!$C$2:$C${n},$A{r},Defects!$J$2:$J${n},"{st}")').font = FONT
        s.cell(row=r, column=6, value=f"=SUM(B{r}:E{r})").font = BOLD
    s.cell(row=8, column=1, value="Total").font = BOLD
    for col in range(2, 7):
        L = get_column_letter(col)
        s.cell(row=8, column=col, value=f"=SUM({L}5:{L}7)").font = BOLD
    for i, w in enumerate([12, 10, 10, 16, 14, 10], 1):
        s.column_dimensions[get_column_letter(i)].width = w
    wb.save(HERE / "Defect_Register.xlsx")
    return Counter((x[2], x[9]) for x in DEFECTS)


if __name__ == "__main__":
    print(json.dumps(build_test_cases(), indent=1))
    print(build_defects())
