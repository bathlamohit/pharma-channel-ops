# 0006. Email text is data: fixed form, identity from the mailbox rule, rules enforced in code

- Status: Accepted
- Date: 2026-11-18 (form cleaning added 2026-11-20 after the live run)

## Context
`claim_emails.csv` is free text in mixed formats and languages. EML-017 contains a prompt
injection; EML-011 comes from a personal address claiming to be a known stockist; EML-018 has
no details at all.

## Decision
- The model fills a fixed Pydantic form (`ExtractedEmail`): kind (claim / status_query /
  not_a_claim), one entry per claim line copied as written, and any claim numbers mentioned.
  Its system prompt says the email is data and to ignore instructions in it.
- Routing reads only the structured `kind`, never the text.
- The sender is identified only by `stockist_code_by_mailbox_rule`. The form has no stockist
  field, so an email cannot claim to be another stockist. No code means a person looks.
- Code, not the prompt, enforces the form's rules (`clean_form`): lines with no product, batch or
  quantity are dropped; a claim type other than breakage or short supply is ignored, because
  near expiry vs expired is set from the batch master's expiry.
- Code normalises what the model copied: expiry text to a month, invoice references to the
  standard form, a letter O in a batch number only when exactly one batch matches (and the
  correction is flagged).
- All seven checks run on every claim line, whatever the email says.
- A status reply states only register facts for the sender's own claims; another stockist's claim
  is reported as "no such claim on this stockist's account".
- One retry if the model fails or returns a malformed form, then a person.

## Alternatives considered
- **Keyword filter for injections.** Rejected: rewording beats it; structure does not.
- **Let the model map product names to SKU codes.** Rejected: the batch master gives the SKU.

## Consequences
- With gpt-4o-mini, 30 of 30 emails match the agreed forms (`pytest -q -m live`).
- The live run found the model sets claim types and empty lines despite the prompt; code now
  removes both.
