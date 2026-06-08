"""Before trusting reference tokens as a matching key, check whether they actually
identify transactions or just recur as boilerplate.

A token shared by hundreds of rows (an account marker, a bank's standing prefix)
identifies nothing, and matching on it produces false pairs. A token that appears on one
ledger row and one statement row is a strong identity signal. This prints the frequency
distribution so we know which regime we're in, and confirms the many-to-one direction
while we're here. Run with `python -m matching.diagnose_tokens`.
"""

from collections import Counter

from ingest import load
from matching.compare import _distinctive_tokens


def main():
    data = load()

    ledger_df = Counter()
    for row in data.ledger:
        for token in _distinctive_tokens(row):
            ledger_df[token] += 1
    statement_df = Counter()
    for row in data.statement:
        for token in _distinctive_tokens(row):
            statement_df[token] += 1

    all_tokens = set(ledger_df) | set(statement_df)
    print(f"distinct distinctive tokens: {len(all_tokens):,}")
    print()

    # How often does a token appear across rows? Cross-side identity wants tokens that are
    # rare on both sides.
    combined = Counter()
    for token in all_tokens:
        combined[token] = ledger_df[token] + statement_df[token]

    buckets = Counter()
    for token, freq in combined.items():
        if freq == 1:
            buckets["appears once total"] += 1
        elif freq == 2:
            buckets["appears twice (ideal: one each side)"] += 1
        elif freq <= 5:
            buckets["3 to 5 rows"] += 1
        elif freq <= 20:
            buckets["6 to 20 rows"] += 1
        else:
            buckets["more than 20 rows (boilerplate)"] += 1

    print("token frequency across all rows:")
    for label in ["appears once total", "appears twice (ideal: one each side)",
                  "3 to 5 rows", "6 to 20 rows", "more than 20 rows (boilerplate)"]:
        print(f"  {label}: {buckets[label]:,}")
    print()

    print("most common tokens (these are the noise risk):")
    for token, freq in combined.most_common(10):
        print(f"  {token!r}: {freq:,} rows")
    print()

    # Many-to-one direction: do several statement rows ever map to one allocation that's a
    # single ledger row's allocation? Confirm the splits can go both ways.
    alloc_to_statements = Counter()
    for s in data.statement:
        for a in s.true_allocations:
            alloc_to_statements[a] += 1
    many_statements = sum(1 for c in alloc_to_statements.values() if c > 1)
    print(f"allocations claimed by more than one statement row (many-to-one): {many_statements:,}")


if __name__ == "__main__":
    main()
