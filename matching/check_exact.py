"""See what the exact tier clears, and whether it's right.

Because we have the true allocations, we can measure exact-match precision directly: of
the statement rows it claimed to match, how many predicted an allocation that's actually
in the truth set. Precision matters more than volume here, in line with the benchmark's
better-to-skip-than-mismatch rule. Run with `python -m matching.check_exact`.
"""

from ingest import load
from matching import exact


def _is_correct(match, statement_by_id):
    """A prediction is correct if its allocation set is a subset of (or equal to) the
    true set, matching the benchmark's scoring rule."""
    truth = set(statement_by_id[match.statement_id].true_allocations)
    predicted = set(match.predicted_allocations)
    return bool(predicted) and predicted.issubset(truth)


def main():
    data = load()
    statement_by_id = {s.row_id: s for s in data.statement}

    matches, unmatched, used = exact.run(data.ledger, data.statement)

    print(f"statement rows in:        {len(data.statement):,}")
    print(f"cleared by exact tier:    {len(matches):,}")
    print(f"left for later tiers:     {len(unmatched):,}")
    print(f"ledger rows consumed:     {len(used):,}")
    print()

    correct = sum(1 for m in matches if _is_correct(m, statement_by_id))
    if matches:
        precision = correct / len(matches)
        print(f"exact-tier precision:     {precision:.1%}  ({correct:,}/{len(matches):,} correct)")
    else:
        print("exact tier matched nothing in this sample")


if __name__ == "__main__":
    main()
