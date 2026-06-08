"""The result type every matching tier produces.

A Match records which statement row was paired with which ledger row(s), how confident we
are, which tier decided it, and a short human reason. The predicted allocation is built
from the matched ledger rows' allocation keys, which is what scoring compares to truth.
"""

from dataclasses import dataclass, field


@dataclass
class Match:
    statement_id: str
    ledger_ids: list[str]
    predicted_allocations: list[str]
    confidence: float
    tier: str                      # which stage resolved it: exact, fuzzy, split
    reason: str
    score_detail: dict = field(default_factory=dict)


def match_from_ledger(statement_row, ledger_rows, confidence, tier, reason, score_detail=None):
    """Build a Match by reading the prediction primitives off the matched ledger rows."""
    return Match(
        statement_id=statement_row.row_id,
        ledger_ids=[row.row_id for row in ledger_rows],
        predicted_allocations=[row.allocation for row in ledger_rows if row.allocation],
        confidence=confidence,
        tier=tier,
        reason=reason,
        score_detail=score_detail or {},
    )
