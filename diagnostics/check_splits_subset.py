"""The benchmark counts a prediction correct if it is a subset of the true allocation set.
A split row's truth is several allocations; if the scored tier matched that row to one
ledger row whose allocation is one of those true allocations, that single-element
prediction is a valid subset, so it should count as correct. This checks how many split
rows the scored tier already gets right under the subset rule, which decides whether a
dedicated split solver is even needed. Run with `python -m diagnostics.check_splits_subset`.
"""

from ingest import load
from matching import exact, scored
from matching.token_weights import TokenWeights


def main():
    data = load()
    statement_by_id = {s.row_id: s for s in data.statement}
    weights = TokenWeights(data.ledger + data.statement)

    _, after_exact, used = exact.run(data.ledger, data.statement)
    remaining_ledger = [l for l in data.ledger if l.row_id not in used]
    scored_matches, _, _ = scored.run(remaining_ledger, after_exact, weights)

    split_ids = {s.row_id for s in data.statement if len(set(s.true_allocations)) > 1}
    print(f"split statement rows (truth spans several allocations): {len(split_ids):,}")

    matched_split_ids = {m.statement_id for m in scored_matches if m.statement_id in split_ids}
    print(f"  of those, the scored tier produced a match for:        {len(matched_split_ids):,}")

    correct_subset = 0
    for m in scored_matches:
        if m.statement_id not in split_ids:
            continue
        truth = set(statement_by_id[m.statement_id].true_allocations)
        predicted = set(m.predicted_allocations)
        if predicted and predicted.issubset(truth):
            correct_subset += 1

    print(f"  scored-tier picks that are a valid subset of the truth: {correct_subset:,}")
    print()
    if matched_split_ids:
        print(f"so {correct_subset:,} of the {len(matched_split_ids):,} matched split rows already "
              f"count as correct under the benchmark's subset rule, with no split solver.")


if __name__ == "__main__":
    main()
