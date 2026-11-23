# 0005. Clean the extracts once at build time, log every fix, keep original line numbers

- Status: Accepted
- Date: 2026-11-16

## Context
The extracts are dirty, and the dirt changes the numbers: the first analysis mis-flagged Rs 15 L
of claims because of stockist-code casing. Citations must still point at lines a person can open
in the raw file.

## Decision
`scripts/build_tables.py` reads `data/raw/` (never edited) and writes `data/clean/` plus
`fix_log.csv`. Every cleaned row keeps `src_line`, its line in the raw file. Fixes:

- dates in three formats -> ISO
- stockist codes padded or lower-case; SKU codes `PFL-1001`; CFA codes `CFE01` -> `CF-E01`
- exact duplicate rows dropped (23 claims, 745 sales lines)
- blank claim values priced at quantity x PTS; comma-formatted numbers
- scheme codes `""`, `NA`, `-` -> none
- blank snapshot expiry filled from the batch master when the row has a batch. The 270 blank
  expiries in this extract are all stock-out rows (no batch, zero packs) and are left as they are.
- whole-number columns written as integers (13987, not 13987.0)

The fix log holds only real changes: a date already in ISO, or a value already in its target
form, is not logged. 48,071 entries.

Invoice references (`INV-W01/...`, `INV-S02-2510-053444`) are normalised at lookup time, not in
the cleaned table, so the back-test can still reproduce the verified analysis, which matched them
as written.

## Alternatives considered
- **Clean on every request.** Rejected: slow cold starts on Vercel and risk of drift.
- **Edit the raw CSVs.** Rejected: loses the audit trail.

## Consequences
- Re-run the script after any change to raw data or cleaning rules; tests check the known counts.
- `data/clean/` is committed so the deployed function needs no build step (see 0010).
