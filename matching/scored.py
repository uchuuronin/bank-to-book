"""Scored one-to-one matching with global resolution.

The reference text turns out not to join the two sides: for most true matches the bank's
reference and the ledger's reference describe the same transaction in unrelated words. The
only signal that reliably joins them is amount and date, a credit mirrored against a debit
on or near the same day. That signal is ambiguous on its own, since unrelated transactions
share round amounts, so we generate every amount-and-date-compatible candidate and let the
Hungarian algorithm pick the globally best assignment. Reference tokens, when they happen
to align, sharpen the score as a tie-breaker rather than gating which pairs are considered.

Blocking by rounded amount keeps the candidate set tractable: we only compare rows whose
magnitudes fall in the same bucket, plus neighbours, rather than all against all.
"""

from collections import defaultdict

import numpy as np
from scipy.optimize import linear_sum_assignment

import config
from matching.compare import amounts_match, dates_match
from matching.result import match_from_ledger
from matching.score import score


def _amount_bucket(amount):
    """Group rows by magnitude so candidates only need checking within and around a bucket.
    The bucket width scales with size, since tolerance is relative."""
    magnitude = abs(amount)
    if magnitude == 0:
        return 0
    # Bucket on a log-ish scale by rounding the magnitude to a few significant figures.
    width = max(config.AMOUNT_ABSOLUTE_FLOOR, config.AMOUNT_RELATIVE_TOLERANCE * magnitude)
    return round(magnitude / width)


def _candidate_pairs(ledger_rows, statement_rows):
    """For each statement row, the ledger rows in the same account and currency whose
    amount and date are compatible. Bucketing by amount avoids the full quadratic scan;
    we check the row's bucket and its immediate neighbours to catch boundary cases."""
    by_bucket = defaultdict(list)
    for ledger in ledger_rows:
        by_bucket[(ledger.account, ledger.currency, _amount_bucket(ledger.amount))].append(ledger)

    pairs = defaultdict(dict)
    for s_index, statement in enumerate(statement_rows):
        bucket = _amount_bucket(statement.amount)
        for neighbour in (bucket - 1, bucket, bucket + 1):
            key = (statement.account, statement.currency, neighbour)
            for ledger in by_bucket.get(key, []):
                if amounts_match(ledger.amount, statement.amount) and dates_match(
                    ledger.value_date, statement.value_date
                ):
                    pairs[s_index][ledger.row_id] = ledger
    return pairs


def run(ledger_rows, statement_rows, weights):
    """Return (matches, unmatched_statements, used_ledger_ids).

    Builds a cost matrix over amount-and-date-compatible candidate pairs, solves it
    globally, and commits only the assignments that clear the confidence threshold.
    """
    candidates = _candidate_pairs(ledger_rows, statement_rows)
    if not candidates:
        return [], list(statement_rows), set()

    statement_indices = sorted(candidates)
    ledger_by_id = {}
    for ledgers in candidates.values():
        ledger_by_id.update(ledgers)
    ledger_pool = sorted(ledger_by_id.values(), key=lambda row: row.row_id)
    ledger_position = {ledger.row_id: i for i, ledger in enumerate(ledger_pool)}

    # Hungarian minimises cost, so we store (1 - score) and non-candidate pairs get a cost
    # above any real one. Details are kept alongside to explain the chosen matches.
    forbidden = 2.0
    cost = np.full((len(statement_indices), len(ledger_pool)), forbidden)
    detail_grid = {}

    for r, s_index in enumerate(statement_indices):
        statement = statement_rows[s_index]
        for ledger in candidates[s_index].values():
            value, detail = score(ledger, statement, weights)
            c = ledger_position[ledger.row_id]
            cost[r, c] = 1.0 - value
            detail_grid[(r, c)] = (value, detail)

    rows, cols = linear_sum_assignment(cost)

    matches = []
    matched_statement_indices = set()
    used_ledger_ids = set()
    for r, c in zip(rows, cols):
        if cost[r, c] >= forbidden:
            continue  # this pairing was never a real candidate
        value, detail = detail_grid[(r, c)]
        if value < config.MATCH_ACCEPT_THRESHOLD:
            continue  # too weak to commit; leave for splits or review
        s_index = statement_indices[r]
        statement = statement_rows[s_index]
        ledger = ledger_pool[c]
        matches.append(
            match_from_ledger(
                statement,
                [ledger],
                confidence=round(value, 3),
                tier="scored",
                reason="best global assignment on amount, date and reference agreement",
                score_detail=detail,
            )
        )
        matched_statement_indices.add(s_index)
        used_ledger_ids.add(ledger.row_id)

    unmatched = [s for i, s in enumerate(statement_rows) if i not in matched_statement_indices]
    return matches, unmatched, used_ledger_ids