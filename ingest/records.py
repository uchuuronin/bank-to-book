"""The typed records every later stage works with.

After ingest, nothing touches the raw dataframe. The matcher, verifier, and report all
operate on these two record types, so the messy column layout is dealt with exactly once.
"""

from dataclasses import dataclass, field
from datetime import date


@dataclass
class LedgerRow:
    """An internal ledger entry (the A side). It carries its own allocation key, which is
    the string our matcher predicts when it pairs a statement row to this one."""

    row_id: str
    amount: float          # signed: credits positive, debits negative (see ingest)
    value_date: date | None
    import_date: date | None
    currency: str
    account: str
    debit_or_credit: str
    references: str        # free-text, whitespace-collapsed
    attributes: str
    allocation: str        # the A_allocation key, used as the prediction primitive


@dataclass
class StatementRow:
    """An external bank statement entry (the B side). This is what we try to match. Its
    true allocation (one or several keys) lives in the dataset's label, which we keep
    separate so the matcher never sees it during matching, only scoring does."""

    row_id: str
    amount: float
    value_date: date | None
    import_date: date | None
    currency: str
    account: str
    debit_or_credit: str
    references: str
    attributes: str
    true_allocations: list[str] = field(default_factory=list)  # ground truth, for scoring only


@dataclass
class Ledgers:
    """The whole ingested dataset: the two sides plus anything we couldn't parse cleanly,
    kept rather than dropped so the pipeline can report what it set aside."""

    ledger: list[LedgerRow]
    statement: list[StatementRow]
    quarantined: list[dict]
