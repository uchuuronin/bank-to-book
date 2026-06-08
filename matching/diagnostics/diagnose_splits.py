"""Measure the real split structure before writing the subset-sum tier.

A split is a statement row whose true allocation points to several ledger rows. For a
subset-sum matcher to be the right tool, those ledger rows' amounts should sum to the
statement amount within tolerance. This checks that assumption and sizes the problem: how
many ledger rows per split, and how often they actually sum. If they don't sum, subset-sum
is the wrong approach and we find out now. Run with `python -m matching.diagnose_splits`.
"""

from collections import Counter

import config
from ingest import load
from matching.compare import amounts_match


def main():
    data = load()

    # Group ledger rows by their allocation key so we can pull the set of ledger rows that
    # back a given statement row's true allocation.
    ledger_by_allocation = {}
    for l in data.ledger:
        ledger_by_allocation.setdefault(l.allocation, []).append(l)

    multi = [s for s in data.statement if len(s.true_allocations) > 1]
    print(f"statement rows whose true match spans several allocations: {len(multi):,}")
    print()

    size_counts = Counter()
    summed_clean = 0
    summed_off = 0
    ledger_missing = 0
    examples = []

    for s in multi:
        ledger_rows = []
        for alloc in s.true_allocations:
            ledger_rows.extend(ledger_by_allocation.get(alloc, []))

        size_counts[len(s.true_allocations)] += 1

        if not ledger_rows:
            ledger_missing += 1
            continue

        # Do the backing ledger rows sum to the statement amount? Sum their signed amounts
        # and compare magnitude against the statement, since the two sides mirror in sign.
        ledger_sum = sum(l.amount for l in ledger_rows)
        if amounts_match(ledger_sum, s.amount):
            summed_clean += 1
        else:
            summed_off += 1
            if len(examples) < 5:
                examples.append((s, ledger_rows, ledger_sum))

    print("ledger rows backing each split (by allocation count):")
    for size in sorted(size_counts):
        print(f"  {size} allocations: {size_counts[size]:,} statement rows")
    print()

    print(f"splits whose ledger rows sum to the statement amount: {summed_clean:,}")
    print(f"splits whose ledger rows do NOT sum cleanly:           {summed_off:,}")
    print(f"splits where backing ledger rows aren't in the sample: {ledger_missing:,}")
    print()

    if examples:
        print("examples that did not sum (is subset-sum the wrong tool, or is it noise?):")
        print()
        for s, ledger_rows, ledger_sum in examples:
            print(f"  statement amount {s.amount:,.2f}, backed by {len(ledger_rows)} ledger rows "
                  f"summing to {ledger_sum:,.2f}")
            for l in ledger_rows[:6]:
                print(f"    ledger {l.amount:,.2f}")
            print()


if __name__ == "__main__":
    main()
