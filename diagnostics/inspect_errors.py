"""Two hypotheses (token support, candidate competition) failed to explain the scored
tier's errors, so look at the raw failing rows instead of aggregate stats. The errors
concentrate in single-candidate matches whose true answer is no-match or a split. Print
those rows in full so we can see what a human would notice: amount exactness, date gap,
how the matched ledger row's own allocation relates to the statement's truth. Run with
`python -m diagnostics.inspect_errors`.
"""

from ingest import load
from matching import exact, scored
from matching.compare import amount_distance
from matching.token_weights import TokenWeights


def main():
    data = load()
    statement_by_id = {s.row_id: s for s in data.statement}
    ledger_by_id = {l.row_id: l for l in data.ledger}
    weights = TokenWeights(data.ledger + data.statement)

    _, after_exact, used = exact.run(data.ledger, data.statement)
    remaining_ledger = [l for l in data.ledger if l.row_id not in used]
    scored_matches, _, _ = scored.run(remaining_ledger, after_exact, weights)

    no_match_errors = []
    wrong_single_errors = []
    for m in scored_matches:
        truth = statement_by_id[m.statement_id].true_allocations
        predicted = set(m.predicted_allocations)
        if predicted and set(predicted).issubset(set(truth)):
            continue
        if len(truth) == 0:
            no_match_errors.append(m)
        elif len(truth) == 1:
            wrong_single_errors.append(m)

    print("False positives, where the statement row truly has no match:")
    print()
    for m in no_match_errors[:6]:
        s = statement_by_id[m.statement_id]
        l = ledger_by_id[m.ledger_ids[0]]
        gap_days = abs((l.value_date - s.value_date).days) if l.value_date and s.value_date else "?"
        print(f"  statement   {s.amount:>18,.2f}   {s.value_date}   {s.references[:55]}")
        print(f"  matched to  {l.amount:>18,.2f}   {l.value_date}   {l.references[:55]}")
        print(f"  amount gap {amount_distance(l.amount, s.amount):,.2f}, date gap {gap_days} days, "
              f"confidence {m.confidence}")
        print()

    print("Wrong single, where a real match existed but the wrong ledger row was picked:")
    print()
    for m in wrong_single_errors[:6]:
        s = statement_by_id[m.statement_id]
        l = ledger_by_id[m.ledger_ids[0]]
        print(f"  statement        {s.amount:>18,.2f}   {s.value_date}   {s.references[:55]}")
        print(f"  picked ledger    {l.amount:>18,.2f}   {l.value_date}   {l.references[:55]}")
        print(f"  picked allocation   {l.allocation[:65]}")
        print(f"  true allocation     {s.true_allocations[0][:65]}")
        print(f"  amount gap {amount_distance(l.amount, s.amount):,.2f}, confidence {m.confidence}")
        print()


if __name__ == "__main__":
    main()
