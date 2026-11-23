from agent.guard import PLACEHOLDER, cite_and_format


def test_uncited_number_is_stripped():
    state = {"lines": [{"claim": {"batch_no": "K2430146"}, "errors": [],
                        "checks": {"chk_quantity": {"detail": "705 claimed against 441 supplied", "clause": "RP 5.5"}}}],
                 "model_text": ["explanation", "reply"],
             "explanation": "705 packs claimed but only 441 supplied; worth Rs 99,999."}
    out = cite_and_format(state)
    assert "705" in out["explanation"] and "441" in out["explanation"]
    assert "99,999" not in out["explanation"] and PLACEHOLDER in out["explanation"]
    assert out["errors"]


def test_policy_clauses_are_kept():
    state = {"lines": [{"claim": {}, "errors": [], "checks": {"chk_duplicate": {
        "detail": "Already claimed as CLM-2607-01744", "clause": "CF 2.6.3"}}}],
                 "model_text": ["explanation", "reply"],
             "explanation": "Rejected under CF 2.6.3: already claimed as CLM-2607-01744."}
    out = cite_and_format(state)
    assert out["explanation"] == state["explanation"] and not out["errors"]


def test_status_reply_may_state_register_facts():
    state = {"status_facts": ["CLM-2608-02444: Pending, raised 2026-08-17"], "model_text": ["reply"],
             "reply": "Your claim CLM-2608-02444 raised 2026-08-17 is pending; credit of 5000 soon."}
    out = cite_and_format(state)
    assert "2608-02444" in out["reply"] and "5000" not in out["reply"]


def test_code_written_text_is_not_filtered():
    """Templates (ADR 0012) state code facts such as 'within 30 days'; only model text is guarded."""
    state = {"explanation": "Credit 38 packs, Rs 5,749.40; credit note within 30 days."}
    assert cite_and_format(state) == {"errors": []}
