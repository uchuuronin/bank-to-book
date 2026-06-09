"""Subset-sum is out: only 24 of 352 splits sum to the statement amount. The examples
show several statement rows sharing one set of ledger rows under a common allocation, so
a split is grouped by shared allocation membership, not by an amount sum. This looks at
the actual allocation-key strings in a few split groups to see what connects them, so we
can build the right grouping rule instead of guessing. Run with
`python -m matching.inspect_splits`.
"""

from collections import Counter

from ingest import load


def main():
    data = load()

    multi = [s for s in data.statement if len(s.true_allocations) > 1]

    print(f"multi-allocation statement rows: {len(multi):,}")

    # The 2-key examples show identical keys repeated. Check how many "splits" are really
    # one allocation listed more than once, versus genuinely distinct allocations.
    collapse_to_one = 0
    still_multi = 0
    distinct_counts = Counter()
    for s in multi:
        distinct = set(s.true_allocations)
        distinct_counts[len(distinct)] += 1
        if len(distinct) == 1:
            collapse_to_one += 1
        else:
            still_multi += 1

    print(f"  collapse to a single allocation once deduped: {collapse_to_one:,}")
    print(f"  genuinely span several distinct allocations:  {still_multi:,}")
    print()
    print("distinct allocation count after dedup:")
    for n in sorted(distinct_counts):
        print(f"  {n} distinct: {distinct_counts[n]:,}")
    print()

    # Look at a few small split groups in full: the statement row's own fields, and the
    # list of true allocation keys it points to, to see their shared structure.
    print("a few splits in detail (statement row and its true allocation keys):")
    print()
    shown = 0
    for s in multi:
        if len(s.true_allocations) not in (2, 3):
            continue
        if shown >= 4:
            break
        print(f"  statement amount {s.amount:,.2f}  date {s.value_date}  acct {s.account}")
        print(f"  statement refs:  {s.references[:70]}")
        print(f"  statement attrs: {s.attributes[:70]}")
        print(f"  true allocation keys ({len(s.true_allocations)}):")
        for a in s.true_allocations:
            print(f"    {a[:90]}")
        print()
        shown += 1

    # Do the allocation keys within one split share a common prefix (currency_date_account)
    # or some other structure? Check how much of the key is shared across the group.
    print("within-group key structure (do the keys in a split share a prefix?):")
    print()
    checked = 0
    for s in multi:
        if len(s.true_allocations) < 2:
            continue
        if checked >= 5:
            break
        keys = s.true_allocations
        # Longest common prefix across the group's keys.
        prefix = keys[0]
        for k in keys[1:]:
            while not k.startswith(prefix) and prefix:
                prefix = prefix[:-1]
        print(f"  group of {len(keys)} keys, shared prefix: {prefix[:70]!r}")
        checked += 1


if __name__ == "__main__":
    main()