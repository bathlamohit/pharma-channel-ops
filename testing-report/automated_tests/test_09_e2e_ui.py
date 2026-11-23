"""Browser end-to-end tests with Playwright (headless Chromium) against a real server.
Each journey is a real user path: click, type, read what the page shows, and compare with the API.
Screenshots of key states go to evidence/screenshots; a failing test saves a full-page screenshot."""
import re

import httpx
import pytest
from playwright.sync_api import expect, sync_playwright

SHOTS = None


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()


@pytest.fixture
def page(browser, server):
    from conftest import EVIDENCE
    global SHOTS
    SHOTS = EVIDENCE / "screenshots"
    ctx = browser.new_context(viewport={"width": 1400, "height": 900})
    pg = ctx.new_page()
    pg.errors = []
    pg.on("pageerror", lambda e: pg.errors.append(str(e)))
    pg.on("console", lambda m: pg.errors.append(m.text) if m.type == "error" else None)
    pg.goto(server["base"])
    yield pg
    ctx.close()


def tab(page, name):
    page.get_by_role("tab", name=name).click()


def claims(page):
    """The visible claims desk (other tabs stay mounted but hidden)."""
    return page.locator("div:not([hidden]) > .desk")


def shot(page, name):
    page.screenshot(path=str(SHOTS / f"{name}.png"))


def test_digest_loads_and_matches_api(page, server):
    """TC-E2E-001 | UI end-to-end | ADR 0016 | Weekly digest is the first tab; every figure on screen equals the API; no console errors"""
    expect(page.locator(".digest-section")).to_have_count(4, timeout=20000)
    api = httpx.get(server["base"] + "/api/digest", timeout=30).json()
    for i, s in enumerate(api["sections"]):
        shown = page.locator(".digest-section").nth(i).locator(".stat strong").all_inner_texts()
        assert shown == [x["value"] for x in s["stats"]]
    shot(page, "01-weekly-digest")
    assert not page.errors, page.errors


def test_digest_link_opens_the_right_place(page):
    """TC-E2E-002 | UI navigation | ADR 0016 | Clicking a digest to-do opens the matching screen on the right claim / CFA / view"""
    expect(page.locator(".digest-section")).to_have_count(4, timeout=20000)
    page.locator(".digest-section").nth(0).locator(".digest-link").first.click()
    expect(page.locator(".case-meta")).to_contain_text("CLM-", timeout=10000)
    tab(page, "Weekly digest")
    page.locator(".digest-section").nth(2).locator(".digest-link").first.click()
    expect(page.locator("div:not([hidden]) > .stockdesk .cfa.active")).to_contain_text("Lucknow", timeout=10000)
    tab(page, "Weekly digest")
    page.locator(".digest-section").nth(3).locator(".digest-link").first.click()
    expect(page.locator("div:not([hidden]) > .stockdesk .view-switch .on")).to_contain_text("Schemes")


def test_claims_inbox_check_and_decide(page):
    """TC-E2E-003 | UI end-to-end | ADR 0002, 0012 | Open EML-014, see part credit; override without reason blocked; decide; second decision refused after reload"""
    tab(page, "Claims desk")
    page.get_by_placeholder("Search stockist, batch, claim or email id").fill("EML-014")
    page.locator(".item").first.click()
    expect(page.locator(".rec-action")).to_have_text("Credit in part", timeout=15000)
    expect(page.locator(".case .summary")).to_contain_text("Read by")
    shot(page, "02-claim-part-credit")
    claims(page).get_by_label("Your name").fill("QA Exec")
    claims(page).get_by_role("button", name="Approve").click()
    expect(page.locator(".decision")).to_contain_text("Recorded approve")
    page.reload()
    tab(page, "Claims desk")
    page.get_by_placeholder("Search stockist, batch, claim or email id").fill("EML-014")
    page.locator(".item").first.click()
    expect(page.locator(".rec-action")).to_be_visible(timeout=15000)
    claims(page).get_by_label("Your name").fill("QA Exec 2")
    claims(page).get_by_role("button", name="Approve").click()
    expect(page.locator(".decision .error")).to_contain_text("Already approved by QA Exec")
    shot(page, "03-second-decision-refused")


def test_override_requires_reason_in_ui(page):
    """TC-E2E-004 | UI validation | ADR 0012 | Approving a recommended reject shows the reason requirement before any request"""
    tab(page, "Claims desk")
    page.get_by_placeholder("Search stockist, batch, claim or email id").fill("EML-010")
    page.locator(".item").first.click()
    expect(page.locator(".rec-action")).to_have_text("Reject", timeout=15000)
    claims(page).get_by_label("Your name").fill("QA Exec")
    claims(page).get_by_role("button", name="Approve").click()
    expect(page.locator(".decision .error")).to_contain_text("goes against the recommendation")


def test_new_claim_by_paste_and_lifecycle(page):
    """TC-E2E-005 | UI end-to-end | ADR 0013 | Paste a new email; claim number shown; open it; verify; approve; credit note; status timeline"""
    tab(page, "Claims desk")
    page.get_by_role("button", name="+ New claim").click()
    page.locator(".new-claim input[list='stockist-list']").fill("STK0096 · ")
    opt = page.locator("#stockist-list option[value^='STK0096']").first.get_attribute("value")
    page.locator(".new-claim input[list='stockist-list']").fill(opt)
    page.locator(".new-claim textarea").fill("Dear sir, batch F2420525, exp May-26, 12 strips, inv INV/W01/2501/026732")
    page.get_by_role("button", name="Check and log claim").click()
    expect(page.locator(".stat-logged")).to_contain_text("CLM-", timeout=15000)
    no = page.locator(".stat-logged .link").first.inner_text()
    shot(page, "04-new-claim-logged")
    page.locator(".stat-logged .link").first.click()
    expect(page.locator(".status-card h3")).to_have_text(re.compile("Status: (Received|Awaiting info)"))
    claims(page).get_by_label("Your name").fill("QA Desk")
    assert claims(page).get_by_role("button", name="Approve").is_disabled()
    page.get_by_role("button", name="Mark verified at CFA").click()
    expect(page.locator(".status-card h3")).to_have_text("Status: Verified")
    claims(page).get_by_role("button", name="Approve").click()
    # dated today, this claim is 174 days past expiry: the recommendation is reject, so approving needs a reason
    expect(page.locator(".decision .error")).to_contain_text("goes against the recommendation")
    claims(page).get_by_label("Reason").fill("Area Manager confirmed the stock was received in time")
    claims(page).get_by_role("button", name="Approve").click()
    expect(page.locator(".status-card h3")).to_have_text("Status: Approved")
    page.get_by_placeholder("Credit note number").fill("CN/QA/0001")
    page.get_by_role("button", name="Record credit note").click()
    expect(page.locator(".status-card h3")).to_have_text("Status: Credit note raised")
    expect(page.locator(".item.active")).to_contain_text(no)
    shot(page, "05-new-claim-credit-note")


def test_new_claim_form_validation(page):
    """TC-E2E-006 | UI validation | ADR 0013 | Claim form without a stockist is refused on the page"""
    tab(page, "Claims desk")
    page.get_by_role("button", name="+ New claim").click()
    page.get_by_role("button", name="Enter a claim form").click()
    page.get_by_role("button", name="Check and log claim").click()
    expect(page.locator(".new-claim .error")).to_contain_text("Pick the stockist")


def test_expiry_dispatch_task_steps(page, server):
    """TC-E2E-007 | UI end-to-end | ADR 0014; plan step 3 | Kolkata to-do equals API; record a consent step; pick order search; batch-order chart"""
    tab(page, "Expiry & dispatch")
    desk = page.locator("div:not([hidden]) > .stockdesk")
    expect(desk.locator(".task").first).to_be_visible(timeout=20000)
    api = httpx.get(server["base"] + "/api/stock/plan?cfa=CF-E01", timeout=30).json()
    assert desk.locator(".task").count() == len(api["todo"])
    desk.get_by_label("Your name").fill("QA Supply")
    desk.locator(".chip", has_text="Bill with consent").click()
    desk.locator(".task").first.locator(".steps button").first.click()
    expect(desk.locator(".task").first.locator(".step.done")).to_contain_text("Offered with stockist consent")
    shot(page, "06-expiry-consent-recorded")
    desk.get_by_role("button", name=re.compile("^Not moving")).click()
    expect(desk.locator(".watch-note")).to_contain_text("Watch list, not a forecast")
    assert desk.locator(".task").count() == len(api["watch"])
    desk.locator(".task").first.get_by_role("button", name="Checked with CFA").click()
    expect(desk.locator(".task").first.locator(".step.done")).to_contain_text("Checked with CFA")
    shot(page, "06b-expiry-not-moving")
    desk.get_by_role("button", name="Pick order").click()
    desk.get_by_placeholder("Find a product or batch").fill("Paracetamol")
    expect(desk.locator(".pick-row")).to_have_count(1)
    desk.get_by_role("button", name=re.compile("Batch-order check")).click()
    expect(desk.locator(".fefo-say")).to_contain_text("71%")
    shot(page, "07-batch-order-check")


def test_short_dated_dispatches(page, server):
    """TC-E2E-012 | UI end-to-end | CO-POL-014 7.1; plan step 4 | National 'where and why' equals the API; Chennai's flagged lines; record 'Agreed'"""
    tab(page, "Expiry & dispatch")
    desk = page.locator("div:not([hidden]) > .stockdesk")
    s = httpx.get(server["base"] + "/api/stock/short-dated", timeout=30).json()
    expect(desk.locator(".short-dated-national summary")).to_contain_text(f"{s['lines']:,}".replace(",", ","), timeout=20000)
    desk.locator(".short-dated-national summary").click()
    expect(desk.locator(".short-dated-national")).to_contain_text("Arrived old from the CDC")
    desk.get_by_label("Your name").fill("QA Supply")
    desk.locator(".cfa", has_text="Chennai").click()
    desk.get_by_role("button", name=re.compile("^Short-dated dispatches")).click()
    expect(desk.locator(".sd-lines tbody tr").first).to_be_visible(timeout=15000)
    assert desk.locator(".sd-lines tbody tr").count() == 50
    desk.locator(".sd-lines tbody tr").first.get_by_role("button", name="Agreed").click()
    expect(desk.locator(".sd-lines tbody tr").first.locator(".step.done")).to_contain_text("Stockist agreed")
    shot(page, "06c-short-dated-dispatches")


def test_allocation_views(page, server):
    """TC-E2E-008 | UI end-to-end | plan step 2 | Lucknow top-ups; basis switch changes the cards; top-up step; returns; shares; what changed; schemes equal the API"""
    tab(page, "Allocation")
    desk = page.locator("div:not([hidden]) > .stockdesk")
    expect(desk.locator(".cfa.active")).to_contain_text("Lucknow", timeout=20000)
    expect(desk.locator(".task").first).to_contain_text("Out of stock")
    ov = httpx.get(server["base"] + "/api/allocation/overview?basis=fy25", timeout=30).json()
    desk.get_by_role("button", name="FY25 (client's instruction)").click()
    lk = next(c for c in ov["cards"] if c["cnf_code"] == "CF-N02")
    expect(desk.locator(".cfa", has_text="Lucknow").locator(".cfa-money")).to_have_text(f"{lk['cover_months']} months")
    desk.get_by_role("button", name="Current (recommended)").click()
    desk.get_by_label("Your name").fill("QA Planner")
    desk.get_by_role("button", name="Top-up from CDC").click()
    expect(desk.locator(".topup-cfa").first).to_be_visible(timeout=10000)
    desk.locator(".topup-cfa").first.locator(".steps button").first.click()
    expect(desk.locator(".topup-cfa").first.locator(".step.done").first).to_contain_text("Allocation raised")
    shot(page, "08a-allocation-topups")
    desk.get_by_role("button", name="Returns to CDC").click()
    expect(desk.locator(".task").first).to_contain_text("Kolkata → CDC", timeout=10000)
    desk.get_by_role("button", name="Shares").click()
    expect(desk.locator(".share-row", has_text="Lucknow")).to_contain_text("short on FY25", timeout=10000)
    shot(page, "08b-allocation-shares")
    desk.get_by_role("button", name="What changed").click()
    expect(desk.locator("table.restate")).to_contain_text("3.31", timeout=10000)
    desk.get_by_role("button", name="Schemes (NSM, CFO)").click()
    sc = httpx.get(server["base"] + "/api/allocation/schemes", timeout=30).json()
    expect(desk.locator(".schemes .stat").first).to_contain_text(f"{sc['scheme_rate'] * 100:.2f}%")
    shot(page, "08-allocation-schemes")


def test_mobile_layout_has_no_sideways_scroll(browser, server):
    """TC-E2E-009 | UI responsive | ADR 0011 | At 375 px every tab fits the width and the claim inbox works"""
    ctx = browser.new_context(viewport={"width": 375, "height": 812}, is_mobile=True)
    pg = ctx.new_page()
    pg.goto(server["base"])
    for name in ("Weekly digest", "Claims desk", "Expiry & dispatch", "Allocation"):
        pg.get_by_role("tab", name=name).click()
        pg.wait_for_timeout(1500)
        assert pg.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), name
    pg.get_by_role("tab", name="Claims desk").click()
    pg.locator(".item").first.click()
    expect(pg.get_by_role("button", name="← Inbox")).to_be_visible(timeout=15000)
    pg.screenshot(path=str(SHOTS / "09-mobile-claim.png"))
    ctx.close()


def test_source_viewer_in_ui(page):
    """TC-E2E-010 | UI end-to-end | ADR 0004 | 'Show rows' on a citation opens the cited rows"""
    tab(page, "Expiry & dispatch")
    desk = page.locator("div:not([hidden]) > .stockdesk")
    expect(desk.locator(".task").first).to_be_visible(timeout=20000)
    desk.locator("details.sources").last.locator("summary").click()
    desk.locator("details.sources").last.get_by_role("button", name="Show rows").first.click()
    expect(desk.locator(".source-rows table")).to_be_visible(timeout=10000)
    assert desk.locator(".source-rows tbody tr").count() > 0


def test_new_claim_default_date_is_local(browser, server):
    """TC-E2E-011 | UI date handling | QA D-07 | At 02:00 in India (20:30 UTC the day before), the new-claim date defaults to the Indian date"""
    from datetime import datetime, timezone
    ctx = browser.new_context(timezone_id="Asia/Kolkata", viewport={"width": 1400, "height": 900})
    pg = ctx.new_page()
    pg.clock.set_fixed_time(datetime(2026, 11, 20, 20, 30, tzinfo=timezone.utc))
    pg.goto(server["base"])
    pg.get_by_role("tab", name="Claims desk").click()
    pg.get_by_role("button", name="+ New claim").click()
    assert pg.locator(".new-claim input[type='date']").input_value() == "2026-11-21"
    ctx.close()
