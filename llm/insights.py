"""Find what is worth saying about the review queue, in code, before any model sees it.

This is the content-selection layer. The hard, valuable part of a briefing is not writing
the sentences, it is deciding which few facts out of a thousand-line queue a reviewer should
act on first. A small language model is poor at that: handed raw counts it tends to restate
them and pad with generic advice. So the selection happens here, deterministically, and the
model is left only the job it is good at, turning these findings into plain English.

Each detector returns a Finding only when there is a real signal, with the exact numbers and
the transaction references it rests on. Detectors that the data cannot support honestly are
left out rather than forced: there is no transposition (divisible-by-nine) test, because a
queue row has no paired counterpart to take a difference against, and no Benford test,
because a few thousand rows is too thin to read without crying wolf. A finding is only ever
produced from something measured, so the briefing has nothing to fabricate.

Findings are ranked by materiality (how much value or how many lines they concern) so the
caller can keep the top few and drop the rest.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, field

import config
from matching import compare
from verify import AMBER, RED


@dataclass
class Finding:
    """One thing worth telling the reviewer, with the evidence attached. `materiality` is a
    sortable score (usually a dollar figure or a line count) used only to rank findings
    against each other; it is not shown. `refs` are real statement-row ids the finding rests
    on, so every claim in the briefing can be traced back to rows in results.csv."""

    kind: str
    materiality: float
    summary: str            # a plain factual statement of the finding, already specific
    refs: list[str] = field(default_factory=list)


def _concentration(rows):
    """Most review queues are bottom-heavy: a few large items hold most of the value while a
    long tail of small ones holds little. If that is true here, the reviewer should start at
    the top, so we measure how much of the total absolute value sits in the largest five."""
    if len(rows) < 5:
        return None
    by_size = sorted(rows, key=lambda r: abs(r.amount), reverse=True)
    total = sum(abs(r.amount) for r in rows)
    if total == 0:
        return None
    top = by_size[:5]
    top_value = sum(abs(r.amount) for r in top)
    share = top_value / total
    if share < 0.30:
        return None  # value is spread evenly, so "start at the top" is not useful advice
    return Finding(
        kind="concentration",
        materiality=top_value,
        summary=(
            f"The five largest lines hold {top_value:,.0f} of the queue's {total:,.0f} total "
            f"value ({share:.0%}); the single largest is {abs(by_size[0].amount):,.0f}."
        ),
        refs=[r.row_id for r in top],
    )


def _largest_single(rows):
    """The one biggest line, called out by amount and date. Even when value is spread, the
    largest single exposure is the natural first thing a reviewer looks at."""
    if not rows:
        return None
    biggest = max(rows, key=lambda r: abs(r.amount))
    if abs(biggest.amount) == 0:
        return None
    date = biggest.value_date.isoformat() if biggest.value_date else "an unknown date"
    return Finding(
        kind="largest",
        materiality=abs(biggest.amount),
        summary=f"The largest unmatched line is {abs(biggest.amount):,.0f}, dated {date}.",
        refs=[biggest.row_id],
    )


def _duplicates(rows):
    """Candidate double-postings: the same payment entered twice. The naive test, lines that
    share an amount, a date and an account, fires far too readily on this data, where a busy
    feed day puts hundreds of distinct transactions on one date in one account and exact-
    amount collisions are then ordinary, not suspicious. A real duplicate also repeats the
    transaction's own reference, so we require a shared distinctive reference token (the same
    identity signal the matcher trusts) on top of amount, date and account. That collapses
    the coincidences and leaves the lines a reviewer would actually treat as duplicates.

    Ranked by how many duplicate groups there are, not by their dollar value, so one large
    coincidental pair cannot push this to the top of the briefing ahead of a real pattern."""
    groups = defaultdict(list)
    for r in rows:
        if r.value_date is None:
            continue
        tokens = compare._distinctive_tokens(r)
        if not tokens:
            continue  # without a reference token we cannot tell a duplicate from a coincidence
        # Key on the rarest shareable token so genuine repeats of one transaction group
        # together, alongside amount, date and account.
        signature_token = min(tokens)
        key = (round(r.amount, 2), r.value_date, r.account, signature_token)
        groups[key].append(r)
    dup_groups = [g for g in groups.values() if len(g) > 1]
    if not dup_groups:
        return None
    dup_lines = sum(len(g) for g in dup_groups)
    biggest_group = max(dup_groups, key=lambda g: len(g))
    amount = abs(biggest_group[0].amount)
    date = biggest_group[0].value_date.isoformat()
    group_word = "group" if len(dup_groups) == 1 else "groups"
    return Finding(
        kind="duplicate",
        materiality=float(dup_lines),
        summary=(
            f"{dup_lines} lines fall into {len(dup_groups)} {group_word} that repeat an exact "
            f"amount, date, account and reference code, the shape of a double-posting; the "
            f"largest such group is {len(biggest_group)} lines of {amount:,.0f} on {date}."
        ),
        refs=[r.row_id for g in dup_groups for r in g][:10],
    )


def _recurring_reference(rows, weights):
    """A reference fragment that recurs across many rows can name a counterparty or payment
    type worth clearing as a batch, but only if the fragment actually distinguishes anything.
    Counting raw word frequency is a trap on this data: the most common word is whatever
    boilerplate sits on nearly every row (a bank's standing text, a product marker), which
    names no counterparty and helps no reviewer. So we rank candidates by recurrence weighted
    by rarity, using the same IDF model the matcher trusts to tell identity from boilerplate.
    A token on almost every row scores near zero however often it appears; a distinctive code
    that recurs on a meaningful minority rises to the top. If nothing clears that bar, we stay
    quiet rather than name a ubiquitous word."""
    counts = Counter()
    rows_with_token = defaultdict(list)
    for r in rows:
        for token in compare._distinctive_tokens(r):
            counts[token] += 1
            rows_with_token[token].append(r.row_id)
    if not counts:
        return None

    # Score each recurring token by how often it appears times how rare it is overall, so a
    # frequent-but-distinctive code wins and frequent boilerplate does not. Only tokens that
    # recur enough to be a "pattern" are eligible.
    floor = max(5, int(len(rows) * 0.05))
    scored = [
        (token, n, n * weights.weight(token))
        for token, n in counts.items()
        if n >= floor
    ]
    if not scored:
        return None
    token, n, _ = max(scored, key=lambda t: t[2])

    # If even the best-scoring token is effectively ubiquitous (low rarity weight), there is
    # no distinctive recurring reference to report.
    if weights.weight(token) < 1.0:
        return None

    return Finding(
        kind="recurring_reference",
        materiality=float(n),
        summary=(
            f"The reference code \"{token}\" recurs on {n} lines, likely one counterparty or "
            f"payment type that can be reviewed as a batch."
        ),
        refs=rows_with_token[token][:10],
    )


def _date_spread(rows):
    """Where in time the queue sits. A single date carrying a large share of the lines points
    at a batch or a feed problem on that day; an even spread does not, and we stay quiet."""
    dated = [r for r in rows if r.value_date is not None]
    if len(dated) < 5:
        return None
    by_day = Counter(r.value_date for r in dated)
    day, n = by_day.most_common(1)[0]
    share = n / len(dated)
    if share < 0.20:
        return None
    return Finding(
        kind="date_spread",
        materiality=float(n),
        summary=(
            f"{n} lines ({share:.0%} of dated lines) fall on {day.isoformat()}, suggesting a "
            f"single batch or feed on that day rather than scattered exceptions."
        ),
        refs=[r.row_id for r in dated if r.value_date == day][:10],
    )


def profile(review_queue, statement_by_id, weights):
    """Run every detector over the queue and return the findings that fired, plus the plain
    counts the caller needs for the overview line. The amber and red bands are profiled
    together here; the counts keep them separate for the overview, because an unconfirmed
    match and a line with no candidate are different problems a reviewer treats differently.

    Detectors measure different things (dollars, line counts) that do not share a scale, so
    we do not sort findings against each other numerically, which would pit a billion-dollar
    concentration against a line count and rank them meaninglessly. Instead we keep a fixed
    reviewer-priority order: what holds the most value, then duplicates worth correcting, then
    the batch-shaped patterns that change how the pile is worked."""
    amber_rows, red_rows = [], []
    for d in review_queue:
        row = statement_by_id.get(d.statement_id)
        if row is None:
            continue
        (amber_rows if d.band == AMBER else red_rows).append(row)
    rows = amber_rows + red_rows

    # Each detector returns a Finding or None. Most read only the rows; the recurring-
    # reference detector also needs the IDF model to tell a distinctive code from boilerplate.
    candidates = [
        _concentration(rows),
        _largest_single(rows),
        _duplicates(rows),
        _recurring_reference(rows, weights),
        _date_spread(rows),
    ]
    findings = [f for f in candidates if f is not None]

    # Concentration and the largest-single call overlap, so when concentration fired (value
    # is top-heavy) the standalone largest-line note is redundant and we drop it.
    if any(f.kind == "concentration" for f in findings):
        findings = [f for f in findings if f.kind != "largest"]

    # Fixed reviewer-priority order rather than a numeric sort across incomparable units.
    priority = {"concentration": 0, "largest": 0, "duplicate": 1,
                "recurring_reference": 2, "date_spread": 3}
    findings.sort(key=lambda f: priority.get(f.kind, 9))

    counts = {
        "total": len(amber_rows) + len(red_rows),
        "amber": len(amber_rows),
        "red": len(red_rows),
    }
    return findings, counts
