"""Load BenchRec into clean typed records.

The file interleaves ledger (A) and statement (B) rows, one side per row. We read it
once, route each row to the right record type, normalize the fields the matcher cares
about, and set aside anything that won't parse instead of silently dropping it.

The allocation label needs care: a statement row's ground truth is either a single
allocation key or a bracketed comma-separated list of them. Since the keys themselves
can contain commas, we split on the boundary between adjacent keys (each key starts with
a currency code like "USD_"), not on every comma.
"""

import re
from datetime import datetime

import pandas as pd

import config
from ingest.records import Ledgers, LedgerRow, StatementRow


def _parse_date(value):
    """BenchRec dates are clean ISO, but a blank or odd value shouldn't crash the row.
    Return None and let the caller decide whether that makes the row unusable."""
    value = (value or "").strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _signed_amount(raw_amount, debit_or_credit):
    """Normalize to a signed float so split sums and comparisons are consistent. The
    dataset already signs amounts, but we make the convention explicit: debits negative,
    credits positive. If the raw value already disagrees with its DR/CR flag we trust the
    flag, since that's the accounting source of truth."""
    amount = float(raw_amount)
    magnitude = abs(amount)
    if debit_or_credit.strip().upper() == "DR":
        return -magnitude
    return magnitude


def _clean_text(value):
    """Collapse the runs of padding whitespace BenchRec uses to align fixed-width fields.
    Without this, fuzzy string matching scores are dominated by spaces."""
    return re.sub(r"\s+", " ", (value or "").strip())


def parse_allocation_label(label):
    """Turn the target label into a list of allocation keys.

    A single match is one bare key. Multiple matches come bracketed:
    "[USD_..._key1,USD_..._key2]". We strip the brackets then split only where one key
    ends and the next begins, detected by the currency-code prefix that opens every key.
    """
    label = (label or "").strip()
    if not label:
        return []
    if label.startswith(config.ALLOCATION_LIST_OPEN) and label.endswith(config.ALLOCATION_LIST_CLOSE):
        label = label[1:-1]
    # Each key starts with something like "USD_". Split before a comma that is followed
    # by such a prefix, so commas inside the attribute text are left alone.
    parts = re.split(r",(?=[A-Z]{3}_)", label)
    cleaned = [p.strip() for p in parts if p.strip()]
    # A prediction is a set: the benchmark scores on set membership, so duplicate keys are
    # noise. Dedupe while preserving first-seen order.
    seen = set()
    unique = []
    for key in cleaned:
        if key not in seen:
            seen.add(key)
            unique.append(key)
    return unique


def _ledger_row(row):
    return LedgerRow(
        row_id=row["A_id"].strip(),
        amount=_signed_amount(row["A_amount"], row["A_debitOrCredit"]),
        value_date=_parse_date(row["A_valueDate"]),
        import_date=_parse_date(row["A_importDate"]),
        currency=row["A_currencyCode"].strip(),
        account=row["A_account"].strip(),
        debit_or_credit=row["A_debitOrCredit"].strip(),
        references=_clean_text(row["A_transactionReferences"]),
        attributes=_clean_text(row["A_transactionAttributes"]),
        allocation=row["A_allocation"].strip(),
    )


def _statement_row(row):
    return StatementRow(
        row_id=row["B_id"].strip(),
        amount=_signed_amount(row["B_amount"], row["B_debitOrCredit"]),
        value_date=_parse_date(row["B_valueDate"]),
        import_date=_parse_date(row["B_importDate"]),
        currency=row["B_currencyCode"].strip(),
        account=row["B_account"].strip(),
        debit_or_credit=row["B_debitOrCredit"].strip(),
        references=_clean_text(row["B_transactionReferences"]),
        attributes=_clean_text(row["B_transactionAttributes"]),
        true_allocations=parse_allocation_label(row[config.LABEL_COLUMN]),
    )


def load(path=None, sample_rows=config.SAMPLE_ROWS):
    """Read the dataset and return clean ledger and statement records.

    sample_rows caps how much we load for fast iteration; pass None for the full file.
    A row goes to ingest if its side's id and amount parse; otherwise it's quarantined
    with the reason, so we never lose a transaction without saying so.
    """
    path = path or config.TRAIN_FILE
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Download BenchRec from Kaggle into data/ (see README)."
        )

    df = pd.read_csv(path, dtype=str, keep_default_na=False, nrows=sample_rows)

    ledger, statement, quarantined = [], [], []
    for position, row in df.iterrows():
        has_a = row["A_id"].strip() != ""
        has_b = row["B_id"].strip() != ""
        try:
            if has_a and not has_b:
                ledger.append(_ledger_row(row))
            elif has_b and not has_a:
                statement.append(_statement_row(row))
            else:
                quarantined.append({"position": position, "reason": "row is neither a clean A nor B side"})
        except (ValueError, KeyError) as problem:
            quarantined.append({"position": position, "reason": str(problem)})

    return Ledgers(ledger=ledger, statement=statement, quarantined=quarantined)
