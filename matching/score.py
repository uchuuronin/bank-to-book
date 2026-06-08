"""Score how well a ledger row matches a statement row, as one number in 0..1.

This replaces the brittle all-or-nothing filters. Instead of requiring amount AND date AND
token to each pass a hard threshold, we combine three pieces of graded evidence so strong
agreement on two can carry a near-miss on the third. That graceful degradation is what
makes matching stable: a true match whose date is a day outside the window, or whose
amount is off by a hair, still scores well if the rare reference codes line up.

The score doubles as the match confidence the verify layer routes on.
"""

import config
from matching.compare import amount_distance


def _amount_similarity(ledger_amount, statement_amount):
    """1.0 when magnitudes are equal (opposite signs), decaying as they diverge. Signs
    that aren't opposite score 0, since a real match mirrors credit against debit."""
    distance = amount_distance(ledger_amount, statement_amount)
    if distance == float("inf"):
        return 0.0
    scale = max(abs(ledger_amount), abs(statement_amount), 1.0)
    return max(0.0, 1.0 - distance / scale)


def _date_similarity(ledger_date, statement_date):
    """1.0 on the same day, fading to 0 across roughly twice the settlement window so a
    date just outside the hard window still contributes something rather than nothing."""
    if ledger_date is None or statement_date is None:
        return 0.0
    gap = abs((ledger_date - statement_date).days)
    span = max(1, config.DATE_WINDOW_DAYS * 2)
    return max(0.0, 1.0 - gap / span)


def _token_bonus(ledger_row, statement_row, weights):
    """Reference tokens join only a minority of true matches, so token agreement is a
    bonus that sharpens an amount-and-date candidate rather than a requirement. We map the
    rarity-weighted shared evidence through a soft curve so any genuine shared code lifts
    the score meaningfully, while its absence simply leaves the amount and date signal to
    stand on its own."""
    shared = weights.shared_weight(ledger_row, statement_row)
    if shared <= 0:
        return 0.0
    # A modest amount of shared rare-token weight already signals identity; saturate so a
    # single strong shared code is worth most of the available bonus.
    return min(1.0, shared / config.TOKEN_BONUS_SATURATION)


def score(ledger_row, statement_row, weights):
    """Blend the signals. Amount and date are the primary join because they are what
    actually link the two sides; a token bonus lifts pairs whose reference codes align,
    which is how genuine matches pull ahead of coincidental amount-twins. Returns the
    score and its parts so the match can record why it was made."""
    amount = _amount_similarity(ledger_row.amount, statement_row.amount)
    date = _date_similarity(ledger_row.value_date, statement_row.value_date)
    token = _token_bonus(ledger_row, statement_row, weights)

    base = config.WEIGHT_AMOUNT * amount + config.WEIGHT_DATE * date
    # The token bonus adds on top of the base and can lift a strong-text pair above an
    # otherwise equal coincidental one, which is what breaks ties in global resolution.
    blended = min(1.0, base + config.WEIGHT_TOKEN * token)
    detail = {"amount": round(amount, 3), "date": round(date, 3), "token": round(token, 3)}
    return blended, detail