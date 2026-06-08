"""Comparison helpers shared by every matching tier.

These encode the rules ingest surfaced from the real data: amounts reach billions so
tolerance is relative; a genuine match has opposite debit/credit signs between the
ledger and statement sides; dates differ by settlement lag within a window. Defining
them once here keeps every tier consistent.
"""

import re

import config


def amounts_match(ledger_amount, statement_amount):
    """A ledger credit mirrors a statement debit, so the two sides carry opposite signs.
    We compare magnitudes and require the signs to actually be opposite."""
    if (ledger_amount >= 0) == (statement_amount >= 0):
        return False
    a, b = abs(ledger_amount), abs(statement_amount)
    tolerance = max(config.AMOUNT_ABSOLUTE_FLOOR, config.AMOUNT_RELATIVE_TOLERANCE * max(a, b))
    return abs(a - b) <= tolerance


def amount_distance(ledger_amount, statement_amount):
    """How far apart two amounts are in magnitude, for scoring fuzzy candidates. Returns
    a large number when signs aren't opposite so such pairs sort to the bottom."""
    if (ledger_amount >= 0) == (statement_amount >= 0):
        return float("inf")
    return abs(abs(ledger_amount) - abs(statement_amount))


def dates_match(ledger_date, statement_date):
    """Equal value dates, or within the settlement window. Missing dates can't confirm a
    match, so they don't."""
    if ledger_date is None or statement_date is None:
        return False
    return abs((ledger_date - statement_date).days) <= config.DATE_WINDOW_DAYS


def same_account_and_currency(ledger_row, statement_row):
    return (
        ledger_row.account == statement_row.account
        and ledger_row.currency == statement_row.currency
    )


def references_strongly_agree(ledger_row, statement_row):
    """Amount, date and sign agreement turns out to be coincidental at this scale: two
    unrelated transactions of the same round amount on the same day collide constantly.
    The reference and attribute text is what actually identifies a transaction, so the
    exact tier uses it to confirm a candidate. We look for a shared distinctive token
    (the alphanumeric reference codes the two sides have in common); pure boilerplate
    words don't count because they appear on unrelated rows too."""
    ledger_tokens = _distinctive_tokens(ledger_row)
    statement_tokens = _distinctive_tokens(statement_row)
    return bool(ledger_tokens & statement_tokens)


def _distinctive_tokens(row):
    """Tokens worth matching on: alphanumeric codes of reasonable length, drawn from both
    the references and attributes. Short fragments and plain dictionary-ish words are too
    common to identify a transaction, so we keep tokens that carry a digit, which is what
    the reference codes in this data look like (e.g. 6660296113, 131C6880)."""
    text = f"{row.references} {row.attributes}".upper()
    tokens = re.findall(r"[A-Z0-9]+", text)
    return {t for t in tokens if len(t) >= config.MIN_TOKEN_LENGTH and any(c.isdigit() for c in t)}