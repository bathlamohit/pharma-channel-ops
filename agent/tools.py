"""Lookup tools: plain Python over the cleaned tables. Exact facts come from here.

Every tool returns {"found": bool, "rows": [...], "citation": Citation} or, when
nothing matches, {"found": False, "reason": ...}. Tools never guess and never fill gaps.
Run `python scripts/build_tables.py` first: tools read data/clean/, not data/raw/.
"""
import re
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from agent.policy import SNAPSHOT_DATE
from agent.state import Citation

CLEAN = Path(__file__).resolve().parent.parent / "data" / "clean"
DATE_COLS = ("mfg_date", "expiry_date", "invoice_date", "claim_date", "snapshot_date",
             "expiry_date_as_claimed", "credit_note_date", "received_date")


@lru_cache(maxsize=None)
def table(name: str) -> pd.DataFrame:
    """One cleaned table, loaded once per process (cold start on Vercel)."""
    path = CLEAN / name
    if not path.exists():
        raise FileNotFoundError(f"{path} missing: run `python scripts/build_tables.py`")
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    for col in df.columns:
        if col in DATE_COLS:
            df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


def group_lists(df: pd.DataFrame, keys: list, col: str, sort: bool = True) -> list[list]:
    """`col` per group as lists, in the order `df.groupby(keys, sort=sort)` returns its groups.
    Same result as `.agg(list)`, without pandas calling Python once per group (87k order lines)."""
    if df.empty:
        return []
    codes = df.groupby(keys, sort=sort).ngroup().to_numpy()
    vals = df[col].to_numpy()[np.argsort(codes, kind="stable")].tolist()
    out, i = [], 0
    for n in np.bincount(codes).tolist():
        out.append(vals[i:i + n])
        i += n
    return out


@lru_cache(maxsize=1)
def _stock_rows() -> pd.DataFrame:
    """The stock snapshot with packs on hand as numbers, converted once per process."""
    st = table("cnf_stock_snapshot.csv").copy()
    st["qty"] = st["qty_on_hand_packs"].astype(float)
    return st


@lru_cache(maxsize=64)
def _on_hand(as_of: pd.Timestamp, keys: tuple) -> pd.Series:
    st = _stock_rows()
    return st[st["snapshot_date"] == as_of].groupby(list(keys))["qty"].sum().rename("qty_on_hand_packs")


def stock_on_hand(as_of, keys: tuple = ("cnf_code", "sku_code")) -> pd.Series:
    """Packs on hand at one snapshot, summed over bin rows, per `keys`."""
    return _on_hand(pd.Timestamp(as_of), tuple(keys)).copy()


def cite(file: str, df: pd.DataFrame) -> Citation:
    return {"file": file, "rows": [int(x) for x in df["src_line"]], "snapshot": SNAPSHOT_DATE.isoformat()}


def _result(file: str, df: pd.DataFrame, reason: str) -> dict:
    if df.empty:
        return {"found": False, "reason": reason, "rows": [], "citation": None}
    return {"found": True, "rows": df.to_dict("records"), "citation": cite(file, df)}


def _norm(code: str | None) -> str:
    return (code or "").strip().upper().replace(" ", "")


def get_stockist(stockist_code: str) -> dict:
    df = table("stockist_master.csv")
    hit = df[df["stockist_code"] == _norm(stockist_code)]
    return _result("stockist_master.csv", hit, f"Stockist {stockist_code!r} not in the stockist master")


def get_sku(sku_code: str) -> dict:
    df = table("sku_master.csv")
    hit = df[df["sku_code"] == _norm(sku_code).replace("-", "")]
    return _result("sku_master.csv", hit, f"SKU {sku_code!r} not in the SKU master")


def get_batch(batch_no: str) -> dict:
    """Batch joined to its SKU. A letter O typed for zero is corrected only when exactly
    one batch matches, and the correction is returned so the page can show it."""
    df = table("batch_master.csv")
    key = _norm(batch_no)
    hit = df[df["batch_no"] == key]
    corrected = None
    if hit.empty and "O" in key[1:]:
        alt = key[0] + key[1:].replace("O", "0")
        alt_hit = df[df["batch_no"] == alt]
        if len(alt_hit) == 1:
            hit, corrected = alt_hit, {"from": batch_no, "to": alt}
    out = _result("batch_master.csv", hit, f"Batch {batch_no!r} not in the batch master")
    if out["found"]:
        out["sku"] = get_sku(out["rows"][0]["sku_code"])
        out["corrected"] = corrected
    return out


def get_supplies(stockist_code: str, batch_no: str | None = None, before=None) -> dict:
    """Invoice lines to a stockist, optionally for one batch and before a date."""
    df = table("primary_sales.csv")
    hit = df[df["stockist_code"] == _norm(stockist_code)]
    if batch_no:
        hit = hit[hit["batch_no"] == _norm(batch_no)]
    if before is not None:
        hit = hit[hit["invoice_date"] < pd.Timestamp(before)]
    return _result("primary_sales.csv", hit, "No supply of this batch to this stockist")


INVOICE = re.compile(r"^INV[-/ ]?([A-Z]\d{2})[-/ ](\d{4})[-/ ](\d{6})$")


def norm_invoice(ref: str | None, fix_prefix: bool = True) -> str:
    """Claims write INV-W01/2504/035230 or INV-S02-2510-053444 for INV/W01/2504/035230.
    fix_prefix=False reproduces the verified back-test, which matched refs as written."""
    key = _norm(ref)
    m = INVOICE.match(key) if fix_prefix else None
    return f"INV/{m[1]}/{m[2]}/{m[3]}" if m else key


def get_claim(claim_no: str) -> dict:
    df = table("expiry_claims.csv")
    hit = df[df["claim_no"] == _norm(claim_no)]
    return _result("expiry_claims.csv", hit, f"Claim {claim_no!r} not in the register")


def get_invoice(invoice_no: str, fix_prefix: bool = True) -> dict:
    df = table("primary_sales.csv")
    hit = df[df["invoice_no"] == norm_invoice(invoice_no, fix_prefix)]
    return _result("primary_sales.csv", hit, f"Invoice {invoice_no!r} not found")


def get_prior_claims(stockist_code: str, batch_no: str | None = None) -> dict:
    """Earlier claims in the register, plus new claims logged since the extract (agent/store.py),
    so a second claim on the same batch counts against the first."""
    from agent import store
    df = table("expiry_claims.csv")
    hit = df[df["stockist_code"] == _norm(stockist_code)]
    if batch_no:
        hit = hit[hit["batch_no"] == _norm(batch_no)]
    out = _result("expiry_claims.csv", hit, "No earlier claims")
    new = store.as_register_rows(_norm(stockist_code), _norm(batch_no) if batch_no else None)
    if new:
        out = {**out, "found": True, "rows": [*out["rows"], *new], "new_claims": [r["claim_no"] for r in new]}
    return out


def get_stock(cnf_code: str | None = None, sku_code: str | None = None, snapshot=None) -> dict:
    """Stock on hand; defaults to the latest snapshot."""
    df = table("cnf_stock_snapshot.csv")
    snap = pd.Timestamp(snapshot) if snapshot else df["snapshot_date"].max()
    hit = df[df["snapshot_date"] == snap]
    if cnf_code:
        hit = hit[hit["cnf_code"] == _norm(cnf_code)]
    if sku_code:
        hit = hit[hit["sku_code"] == _norm(sku_code)]
    return _result("cnf_stock_snapshot.csv", hit, "No stock rows")


# --- Source-row viewer ----------------------------------------------------------------
SOURCE_FILES = ("batch_master.csv", "claim_emails.csv", "cnf_stock_snapshot.csv", "expiry_claims.csv",
                "primary_sales.csv", "sku_master.csv", "stockist_master.csv")
SOURCE_PAGE = 50


@lru_cache(maxsize=None)
def _fixes_by_line(file: str) -> dict[int, list[dict]]:
    """Real changes the build made to each line (entries where nothing changed are left out)."""
    log = table("fix_log.csv")
    log = log[(log["file"] == file) & (log["before"] != log["after"])]
    out: dict[int, list[dict]] = {}
    for r in log.to_dict("records"):
        out.setdefault(int(r["src_line"]), []).append(
            {"field": r["field"], "before": r["before"], "after": r["after"], "fix": r["fix"]})
    return out


def source_rows(file: str, rows: list[int], offset: int = 0, limit: int = SOURCE_PAGE) -> dict:
    """The cleaned rows a citation points at, by original line number, with the fixes made
    to each. A page of `limit` rows at a time: a watch view can cite thousands."""
    if file not in SOURCE_FILES:
        raise ValueError(f"{file!r} is not a source file")
    wanted = list(dict.fromkeys(int(r) for r in rows))
    page = wanted[offset:offset + max(1, min(limit, SOURCE_PAGE))]
    df = table(file)
    hit = df[df["src_line"].astype(int).isin(page)].copy()
    for col in hit.columns:
        if pd.api.types.is_datetime64_any_dtype(hit[col]):
            hit[col] = hit[col].dt.strftime("%Y-%m-%d").fillna("")
    by_line = {int(r["src_line"]): r for r in hit.to_dict("records")}
    fixes = _fixes_by_line(file)
    return {
        "file": file,
        "columns": list(df.columns),
        "total": len(wanted),
        "offset": offset,
        "rows": [by_line[n] for n in page if n in by_line],
        "missing": [n for n in page if n not in by_line],
        "fixes": {str(n): fixes[n] for n in page if n in fixes},
    }
