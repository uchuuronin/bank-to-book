"""Run the deterministic cascade so far (exact pre-pass, then scored global resolution)
and measure it against truth the way the benchmark does: match-rate and precision over the
allocation keys. This is the end-to-end number we steer by; per-tier figures can look good
while the whole cascade under-recovers. Run with `python -m matching.check_cascade`.
"""

from ingest import load
from matching import exact, scored
from matching.token_weights import TokenWeights


def _correct(match, statement_by_id):
    truth = set(statement_by_id[match.statement_id].true_allocations)
    predicted = set(match.predicted_allocations)
    return bool(predicted) and predicted.issubset(truth)


def main():
    data = load()
    statement_by_id = {s.row_id: s for s in data.statement}
    weights = TokenWeights(data.ledger + data.statement)

    exact_matches, after_exact, used = exact.run(data.ledger, data.statement)

    remaining_ledger = [l for l in data.ledger if l.row_id not in used]
    scored_matches, unmatched, _ = scored.run(remaining_ledger, after_exact, weights)

    all_matches = exact_matches + scored_matches

    total_statements = len(data.statement)
    truly_matchable = sum(1 for s in data.statement if s.true_allocations)

    correct = sum(1 for m in all_matches if _correct(m, statement_by_id))
    claimed = len(all_matches)

    print(f"statement rows:               {total_statements:,}")
    print(f"of which truly have a match:  {truly_matchable:,}")
    print()
    print(f"exact tier matched:           {len(exact_matches):,}")
    print(f"scored tier matched:          {len(scored_matches):,}")
    print(f"left unmatched:               {len(unmatched):,}")
    print()
    if claimed:
        print(f"precision: {correct / claimed:.1%}  ({correct:,} correct of {claimed:,} claimed)")
    if truly_matchable:
        print(f"match-rate (recall of true matches): {correct / truly_matchable:.1%}  "
              f"({correct:,} of {truly_matchable:,})")
    print()

    by_tier = {}
    for m in all_matches:
        right = _correct(m, statement_by_id)
        hit, total = by_tier.get(m.tier, (0, 0))
        by_tier[m.tier] = (hit + (1 if right else 0), total + 1)
    print("per-tier precision:")
    for tier, (hit, total) in by_tier.items():
        print(f"  {tier}: {hit / total:.1%}  ({hit:,}/{total:,})")


if __name__ == "__main__":
    main()
