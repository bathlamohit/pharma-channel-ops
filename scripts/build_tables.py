"""Clean the raw extracts once, at build time, and log every fix.

    python scripts/build_tables.py

Reads data/raw/*.csv, writes data/clean/*.csv and data/clean/fix_log.csv.
Every cleaned row keeps `src_line`, its line number in the raw file (header = line 1),
so a citation always points at the original row a person can open.

Fixes (from the Final Plan, section 2 "Data quality"):
- dates in three formats (dd-mm-yyyy, yyyy-mm-dd, dd-Mon-yyyy) -> ISO
- stockist codes padded or lower-case -> stripped, upper-case
- SKU codes with a hyphen (PFL-1001) -> PFL1001
- CFA codes without a hyphen in the stock snapshot (CFE01) -> CF-E01
- exact duplicate rows dropped (745 in sales, 23 in claims)
- blank claim values priced at qty x PTS
- credit values with thousands commas -> numbers
- scheme codes "", "NA", "-" -> none
- blank expiry in the stock snapshot filled from the batch master (stock-out rows have no batch
  and no expiry, and are left as they are)
- whole-number columns written as integers (13987, not 13987.0)
Only real changes are logged: a value already in the target form is not a fix.
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW, CLEAN = ROOT / "data" / "raw", ROOT / "data" / "clean"

DATE_FORMATS = ("%d-%m-%Y", "%Y-%m-%d", "%d-%b-%Y")
DATE_COLS = {
    "batch_master.csv": ["mfg_date", "expiry_date"],
    "primary_sales.csv": ["invoice_date"],
    "expiry_claims.csv": ["claim_date", "expiry_date_as_claimed", "credit_note_date"],
    "cnf_stock_snapshot.csv": ["snapshot_date", "expiry_date"],
    "claim_emails.csv": ["received_date"],
    "stockist_master.csv": ["appointed_on"],
}
CODE_COLS = ["stockist_code", "stockist_code_by_mailbox_rule", "sku_code", "batch_no", "cnf_code"]

fix_log: list[dict] = []


def log(file: str, lines, field: str, before, after, fix: str) -> None:
    for line, b, a in zip(lines, before, after):
        fix_log.append({"file": file, "src_line": int(line), "field": field, "before": b, "after": a, "fix": fix})


def read_raw(name: str) -> pd.DataFrame:
    df = pd.read_csv(RAW / name, dtype=str, keep_default_na=False)
    df.insert(0, "src_line", range(2, len(df) + 2))
    return df


def parse_date(s: str) -> str:
    s = s.strip()
    if not s:
        return ""
    for fmt in DATE_FORMATS:
        try:
            return pd.to_datetime(s, format=fmt).date().isoformat()
        except ValueError:
            continue
    return ""  # unparseable: left blank and logged


def clean_dates(name: str, df: pd.DataFrame) -> None:
    for col in DATE_COLS.get(name, []):
        before = df[col]
        after = before.map(parse_date)
        # Log only odd formats that actually changed; the house format dd-mm-yyyy is just
        # converted, a date already in ISO needs nothing, and an unparseable one is logged below.
        odd = (~before.str.fullmatch(r"\d{2}-\d{2}-\d{4}") & before.ne("")
               & after.ne("") & before.str.strip().ne(after))
        log(name, df.loc[odd, "src_line"], col, before[odd], after[odd], "odd date format to ISO")
        bad = after.eq("") & before.ne("")
        log(name, df.loc[bad, "src_line"], col, before[bad], after[bad], "unparseable date left blank")
        df[col] = after


def clean_codes(name: str, df: pd.DataFrame) -> None:
    for col in CODE_COLS:
        if col not in df:
            continue
        before = df[col]
        after = before.str.strip().str.upper()
        if col == "sku_code":
            after = after.str.replace("-", "", regex=False)
        if col == "cnf_code":  # snapshot has CFE01 for CF-E01 on 165 rows
            after = after.str.replace(r"^CF(?=[A-Z]\d)", "CF-", regex=True)
        changed = before.ne(after)
        log(name, df.loc[changed, "src_line"], col, before[changed], after[changed], "code normalised")
        df[col] = after


def drop_duplicates(name: str, df: pd.DataFrame) -> pd.DataFrame:
    cols = [c for c in df.columns if c != "src_line"]
    dup = df.duplicated(subset=cols, keep="first")
    log(name, df.loc[dup, "src_line"], "*", ["row"] * dup.sum(), [""] * dup.sum(), "exact duplicate dropped")
    return df[~dup]


def to_number(name: str, df: pd.DataFrame, col: str) -> None:
    before = df[col]
    after = before.str.replace(",", "", regex=False).str.strip()
    changed = before.ne(after)
    log(name, df.loc[changed, "src_line"], col, before[changed], after[changed], "number format")
    df[col] = pd.to_numeric(after, errors="coerce")


def whole_numbers_as_int(df: pd.DataFrame) -> pd.DataFrame:
    """A numeric column with a blank turns float in pandas and would be written as 13987.0.
    Columns holding only whole numbers are written as integers, blanks kept blank."""
    for col in df.columns:
        if col != "src_line" and pd.api.types.is_float_dtype(df[col]):
            vals = df[col].dropna()
            if len(vals) and (vals == vals.round()).all():
                df[col] = df[col].astype("Int64")
    return df


def build() -> dict[str, pd.DataFrame]:
    names = sorted(p.name for p in RAW.glob("*.csv"))
    t = {}
    for name in names:
        df = read_raw(name)
        clean_codes(name, df)
        clean_dates(name, df)
        t[name] = drop_duplicates(name, df)

    sku = t["sku_master.csv"]
    sku["pts_inr"] = pd.to_numeric(sku["pts_inr"])
    sku["shelf_life_months"] = pd.to_numeric(sku["shelf_life_months"])
    pts = sku.set_index("sku_code")["pts_inr"]

    sales = t["primary_sales.csv"]
    for col in ["ordered_qty", "invoiced_qty", "free_qty", "pts_inr", "net_value_inr"]:
        to_number("primary_sales.csv", sales, col)
    blank_scheme = sales["scheme_code"].str.strip().isin(["", "NA", "-"])
    odd = blank_scheme & sales["scheme_code"].ne("")
    log("primary_sales.csv", sales.loc[odd, "src_line"], "scheme_code",
        sales.loc[odd, "scheme_code"], [""] * odd.sum(), "no scheme")
    sales.loc[blank_scheme, "scheme_code"] = ""

    claims = t["expiry_claims.csv"]
    for col in ["qty_claimed", "claim_value_inr", "credit_value_inr"]:
        to_number("expiry_claims.csv", claims, col)
    blank = claims["claim_value_inr"].isna()
    priced = claims.loc[blank, "qty_claimed"] * claims.loc[blank, "sku_code"].map(pts)
    log("expiry_claims.csv", claims.loc[blank, "src_line"], "claim_value_inr",
        [""] * blank.sum(), priced.round(2), "priced at qty x PTS")
    claims.loc[blank, "claim_value_inr"] = priced.round(2)

    stock = t["cnf_stock_snapshot.csv"]
    for col in ["qty_on_hand_packs", "avg_monthly_outward_packs"]:
        to_number("cnf_stock_snapshot.csv", stock, col)
    batch_expiry = t["batch_master.csv"].set_index("batch_no")["expiry_date"]
    # Stock-out rows (no batch, zero packs) have no expiry to fill; only rows with a batch are tried.
    blank = stock["expiry_date"].eq("") & stock["batch_no"].ne("")
    filled = stock.loc[blank, "batch_no"].map(batch_expiry).fillna("")
    hit = filled.ne("")
    log("cnf_stock_snapshot.csv", stock.loc[blank & hit.reindex(stock.index, fill_value=False), "src_line"],
        "expiry_date", [""] * hit.sum(), filled[hit], "expiry from batch master")
    stock.loc[blank, "expiry_date"] = filled

    t["batch_master.csv"]["batch_qty_packs"] = pd.to_numeric(t["batch_master.csv"]["batch_qty_packs"])
    return t


def main() -> None:
    CLEAN.mkdir(parents=True, exist_ok=True)
    tables = build()
    for name, df in tables.items():
        whole_numbers_as_int(df).to_csv(CLEAN / name, index=False)
        print(f"{name:28} {len(df):>7} rows")
    pd.DataFrame(fix_log).to_csv(CLEAN / "fix_log.csv", index=False)
    print(f"{'fix_log.csv':28} {len(fix_log):>7} fixes")


if __name__ == "__main__":
    main()
