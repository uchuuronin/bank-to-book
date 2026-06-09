"""Look at the exact tier's wrong matches to find the actual failure mode.

88% precision means the 'exactly one deterministic candidate' rule is committing to some
coincidental pairings. Before tightening the rule we want to see what the wrong matches
have in common: are the amounts only loosely equal (tolerance too wide at billion scale),
are dates landing at the edge of the window, or is the matched ledger row simply not the
one the truth points to. Run with `python -m diagnostics.diagnose_exact`.
"""

from ingest import load
from matching import exact
from matching.compare import amount_distance


def main():
    data = load()
    statement_by_id = {s.row_id: s for s in data.statement}
    ledger_by_id = {l.row_id: l for l in data.ledger}

    matches, _, _ = exact.run(data.ledger, data.statement)

    wrong = []
    for m in matches:
        truth = set(statement_by_id[m.statement_id].true_allocations)
        predicted = set(m.predicted_allocations)
        if not (predicted and predicted.issubset(truth)):
            wrong.append(m)

    print(f"wrong matches: {len(wrong):,} of {len(matches):,}")
    print()

    # How far off were the amounts on the wrong matches? If most are non-zero deltas, the
    # tolerance is letting coincidental near-equal amounts through.
    exact_amount = 0
    near_amount = 0
    for m in wrong:
        statement = statement_by_id[m.statement_id]
        ledger = ledger_by_id[m.ledger_ids[0]]
        delta = amount_distance(ledger.amount, statement.amount)
        if delta == 0:
            exact_amount += 1
        else:
            near_amount += 1
    print(f"wrong matches with exactly equal amounts:  {exact_amount:,}")
    print(f"wrong matches with only near-equal amounts: {near_amount:,}")
    print()

    # Of the wrong ones, did the statement row actually have a true match available at
    # all? If its truth set is empty, the tier matched something that should be unmatched.
    should_be_unmatched = sum(
        1 for m in wrong if not statement_by_id[m.statement_id].true_allocations
    )
    print(f"wrong matches where the statement row truly has NO match: {should_be_unmatched:,}")
    print(f"wrong matches where a real match exists but we picked wrong: {len(wrong) - should_be_unmatched:,}")
    print()

    print("a few wrong matches in detail:")
    for m in wrong[:5]:
        statement = statement_by_id[m.statement_id]
        ledger = ledger_by_id[m.ledger_ids[0]]
        delta = amount_distance(ledger.amount, statement.amount)
        print(f"  statement {statement.row_id}  amount {statement.amount:,.2f}  date {statement.value_date}")
        print(f"    picked ledger {ledger.row_id}  amount {ledger.amount:,.2f}  date {ledger.value_date}  amount gap {delta:,.2f}")
        print(f"    true allocations: {len(statement.true_allocations)}")


if __name__ == "__main__":
    main()
