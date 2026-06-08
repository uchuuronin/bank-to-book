"""Turn raw matches into banded decisions, and decide what to trust automatically.

The confidence band is a deterministic signal, not a model's self-report (which the
research shows is poorly calibrated). The rule comes straight from what the data taught
us: a match corroborated by something beyond amount and date is trustworthy; a match
resting on amount and date alone is plausible but unconfirmable, because unrelated
transactions collide on round amounts; a statement row with no candidate at all is simply
unmatched.

  green  : exact tier, or a scored match with reference-token corroboration -> auto
  amber  : scored match on amount and date alone -> route to review
  red    : no candidate found -> unmatched, route to review

This mirrors how real reconciliation teams work: clear what is certain, send the rest to
a human, never assert a match the evidence cannot support.
"""

from dataclasses import dataclass

import config


GREEN = "green"
AMBER = "amber"
RED = "red"


@dataclass
class Decision:
    statement_id: str
    band: str
    ledger_ids: list[str]
    predicted_allocations: list[str]
    confidence: float
    tier: str
    reason: str


def _band_for(match):
    """Exact-tier matches are corroborated by a shared reference code, so they are green.
    Scored matches are green only if a reference token also supported them; on amount and
    date alone they are amber and go to review."""
    if match.tier == "exact":
        return GREEN
    if match.score_detail.get("token", 0) > 0:
        return GREEN
    return AMBER


def run(matches, unmatched_statements):
    """Band every match and turn unmatched statement rows into red decisions. Returns the
    full decision list plus the subset that needs human review."""
    decisions = []

    for match in matches:
        band = _band_for(match)
        decisions.append(
            Decision(
                statement_id=match.statement_id,
                band=band,
                ledger_ids=match.ledger_ids,
                predicted_allocations=match.predicted_allocations,
                confidence=match.confidence,
                tier=match.tier,
                reason=match.reason,
            )
        )

    for statement in unmatched_statements:
        decisions.append(
            Decision(
                statement_id=statement.row_id,
                band=RED,
                ledger_ids=[],
                predicted_allocations=[],
                confidence=0.0,
                tier="unmatched",
                reason="no ledger candidate within amount and date tolerance",
            )
        )

    review_queue = [d for d in decisions if d.band in (AMBER, RED)]
    return decisions, review_queue
