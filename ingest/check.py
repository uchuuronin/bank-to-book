"""Quick sanity check on ingest. Run `python -m ingest.check` after loading the data to
confirm rows split and normalize the way we expect, before any matching is built on top.
"""

from collections import Counter

from ingest import load


def main():
    data = load()

    print(f"ledger rows:     {len(data.ledger):,}")
    print(f"statement rows:  {len(data.statement):,}")
    print(f"quarantined:     {len(data.quarantined):,}")
    print()

    matched = sum(1 for s in data.statement if s.true_allocations)
    unmatched = sum(1 for s in data.statement if not s.true_allocations)
    print(f"statement rows with a true match:  {matched:,}")
    print(f"statement rows with no match:      {unmatched:,}")
    print()

    multi = Counter(len(s.true_allocations) for s in data.statement if s.true_allocations)
    print("true allocations per matched statement row:")
    for size in sorted(multi):
        print(f"  {size}: {multi[size]:,}")
    print()

    print("sample ledger row:")
    if data.ledger:
        row = data.ledger[0]
        print(f"  id {row.row_id}  amount {row.amount:,.2f}  {row.debit_or_credit}  {row.value_date}")
        print(f"  refs: {row.references[:80]}")
        print(f"  allocation: {row.allocation[:100]}")
    print()

    print("sample statement row:")
    if data.statement:
        row = data.statement[0]
        print(f"  id {row.row_id}  amount {row.amount:,.2f}  {row.debit_or_credit}  {row.value_date}")
        print(f"  refs: {row.references[:80]}")
        print(f"  true allocations: {len(row.true_allocations)}")


if __name__ == "__main__":
    main()
