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
import re

import config
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


def _distinctive_words(text):
    """The human-readable words in a reference string, ignoring the long numeric codes that
    are unique per transaction and say nothing in aggregate. Mirrors the matcher's instinct
    that letters carry the recurring meaning, digits carry the per-row identity."""
    return [w.upper() for w in re.findall(r"[A-Za-z]{%d,}" % config.MIN_TOKEN_LENGTH, text)]


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
    """Lines that share an amount, a date, and an account are candidate double-postings: the
    same payment entered twice, or two genuinely distinct payments that happen to coincide.
    Either way the reviewer wants them surfaced together rather than hit one at a time."""
    groups = defaultdict(list)
    for r in rows:
        if r.value_date is None:
            continue
        key = (round(r.amount, 2), r.value_date, r.account)
        groups[key].append(r)
    dup_groups = [g for g in groups.values() if len(g) > 1]
    if not dup_groups:
        return None
    dup_lines = sum(len(g) for g in dup_groups)
    biggest_group = max(dup_groups, key=lambda g: abs(g[0].amount) * len(g))
    amount = abs(biggest_group[0].amount)
    date = biggest_group[0].value_date.isoformat()
    group_word = "group" if len(dup_groups) == 1 else "groups"
    return Finding(
        kind="duplicate",
        materiality=amount * dup_lines,
        summary=(
            f"{dup_lines} lines fall into {len(dup_groups)} {group_word} sharing an exact "
            f"amount, date and account, which may be double-postings; the largest such group "
            f"is {len(biggest_group)} lines of {amount:,.0f} on {date}."
        ),
        refs=[r.row_id for g in dup_groups for r in g][:10],
    )


def _round_numbers(rows):
    """Suspiciously round amounts (exact thousands, but not the large lines concentration
    already covers) are worth a glance: small round sums are the shape of manual journal
    entries, estimates, and round-sum transfers rather than organic invoiced amounts. A
    cluster of them in the queue is a pattern, not a coincidence."""
    round_rows = [
        r for r in rows
        if r.amount != 0 and round(abs(r.amount)) % 1000 == 0 and abs(r.amount) < 100000
    ]
    if len(round_rows) < 3:
        return None
    value = sum(abs(r.amount) for r in round_rows)
    return Finding(
        kind="round_number",
        materiality=value,
        summary=(
            f"{len(round_rows)} lines are exact multiples of 1,000 (totalling {value:,.0f}), "
            f"the shape of manual entries or transfers rather than invoiced amounts."
        ),
        refs=[r.row_id for r in round_rows][:10],
    )


def _recurring_reference(rows):
    """A word that recurs across many reference strings usually names a counterparty or a
    payment type (a processor, a payroll run, a recurring transfer). If one word dominates
    the queue, those lines are probably one pattern to clear in a batch, not many separate
    puzzles, so naming it changes how the reviewer works the pile."""
    counts = Counter()
    rows_with_word = defaultdict(list)
    for r in rows:
        seen = set(_distinctive_words(r.references))
        for w in seen:
            counts[w] += 1
            rows_with_word[w].append(r.row_id)
    if not counts:
        return None
    word, n = counts.most_common(1)[0]
    if n < max(5, len(rows) * 0.05):
        return None  # nothing recurs often enough to be worth singling out
    return Finding(
        kind="recurring_reference",
        materiality=float(n),
        summary=(
            f"The reference text \"{word.title()}\" recurs on {n} lines, likely one "
            f"counterparty or payment type that can be reviewed as a batch."
        ),
        refs=rows_with_word[word][:10],
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


def profile(review_queue, statement_by_id):
    """Run every detector over the queue and return the findings that fired, most material
    first, plus the plain counts the caller needs for the overview line. The amber and red
    bands are profiled separately, because an unconfirmed match and a line with no candidate
    at all are different problems a reviewer treats differently."""
    amber_rows, red_rows = [], []
    for d in review_queue:
        row = statement_by_id.get(d.statement_id)
        if row is None:
            continue
        (amber_rows if d.band == AMBER else red_rows).append(row)

    findings = []
    for detector in (_concentration, _largest_single, _duplicates, _round_numbers,
                     _recurring_reference, _date_spread):
        # Concentration and the largest-line call overlap, so prefer concentration when it
        # fired and let largest_single stand in only when value is too spread for it.
        result = detector(amber_rows + red_rows)
        if result is not None:
            findings.append(result)
    if any(f.kind == "concentration" for f in findings):
        findings = [f for f in findings if f.kind != "largest"]

    findings.sort(key=lambda f: f.materiality, reverse=True)

    counts = {
        "total": len(amber_rows) + len(red_rows),
        "amber": len(amber_rows),
        "red": len(red_rows),
    }
    return findings, counts
