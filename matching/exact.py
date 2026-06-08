"""Exact match: the cheap, high-confidence first pass.

There's no shared transaction id across the two sides, so 'exact' means a strong
deterministic agreement rather than id equality: same account and currency, opposite
debit/credit signs, amounts equal within the tight relative tolerance, and value dates
that agree within the settlement window. Whatever this clears never reaches the more
expensive tiers.

We index ledger rows by (account, currency) so each statement row only compares against a
small candidate set rather than the whole ledger.
"""

from collections import defaultdict

from matching.compare import amounts_match, dates_match, references_strongly_agree
from matching.result import match_from_ledger


def _index_by_account_currency(ledger_rows):
    index = defaultdict(list)
    for row in ledger_rows:
        index[(row.account, row.currency)].append(row)
    return index


def run(ledger_rows, statement_rows):
    """Return (matches, unmatched_statements, used_ledger_ids).

    A statement row matches here only if exactly one ledger candidate satisfies all the
    deterministic checks. Several candidates means it's ambiguous, so we leave it for the
    fuzzy and resolution tiers, which can weigh competing candidates properly.
    """
    index = _index_by_account_currency(ledger_rows)
    matches = []
    unmatched = []
    used_ledger_ids = set()

    for statement in statement_rows:
        candidates = [
            ledger
            for ledger in index.get((statement.account, statement.currency), [])
            if ledger.row_id not in used_ledger_ids
            and amounts_match(ledger.amount, statement.amount)
            and dates_match(ledger.value_date, statement.value_date)
            and references_strongly_agree(ledger, statement)
        ]

        if len(candidates) == 1:
            ledger = candidates[0]
            used_ledger_ids.add(ledger.row_id)
            matches.append(
                match_from_ledger(
                    statement,
                    [ledger],
                    confidence=1.0,
                    tier="exact",
                    reason="amount, value date and sign agree, and a reference code is shared",
                )
            )
        else:
            unmatched.append(statement)

    return matches, unmatched, used_ledger_ids