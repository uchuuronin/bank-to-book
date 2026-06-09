"""The scored tier is 90% precise; understand its ~90 errors before tuning. Two very
different causes need opposite fixes: a wrong match whose true answer was a single
allocation is a coincidental amount-twin the resolver picked wrong (tighten the gate); a
wrong match whose true answer was several allocations is a split that should never have
been matched 1:1 (leave it for the split tier). We also check whether the wrong matches
had any reference-token support, since token-less commits are the ones a higher threshold
would catch. Run with `python -m diagnostics.diagnose_scored`.
"""

from collections import Counter

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

    wrong = []
    for m in scored_matches:
        truth = set(statement_by_id[m.statement_id].true_allocations)
        predicted = set(m.predicted_allocations)
        if not (predicted and predicted.issubset(truth)):
            wrong.append(m)

    print(f"scored tier: {len(scored_matches):,} matches, {len(wrong):,} wrong")
    print()

    cause = Counter()
    token_support = Counter()
    confidence_band = Counter()
    for m in wrong:
        truth = statement_by_id[m.statement_id].true_allocations
        if len(truth) == 0:
            cause["true answer: no match at all (false positive)"] += 1
        elif len(truth) == 1:
            cause["true answer: a single allocation (coincidental twin picked wrong)"] += 1
        else:
            cause["true answer: multiple allocations (a split, shouldn't be 1:1)"] += 1

        had_token = m.score_detail.get("token", 0) > 0
        token_support["had token support" if had_token else "no token support"] += 1

        c = m.confidence
        if c >= 0.95:
            confidence_band["0.95 and up"] += 1
        elif c >= 0.85:
            confidence_band["0.85 to 0.95"] += 1
        else:
            confidence_band["0.75 to 0.85"] += 1

    print("why each wrong match is wrong:")
    for label, count in cause.most_common():
        print(f"  {label}: {count:,}")
    print()
    print("reference-token support on wrong matches:")
    for label, count in token_support.most_common():
        print(f"  {label}: {count:,}")
    print()
    print("confidence of wrong matches (where a higher threshold would cut):")
    for label in ["0.75 to 0.85", "0.85 to 0.95", "0.95 and up"]:
        print(f"  {label}: {confidence_band[label]:,}")
    print()

    # The decisive question: every WRONG match lacked token support. But how many CORRECT
    # matches also lack it? If correct matches mostly have tokens, then "no token support"
    # cleanly separates good from bad and we can route token-less matches to review. If
    # correct matches are also mostly token-less, requiring tokens would gut recall.
    correct_with_token = 0
    correct_without_token = 0
    for m in scored_matches:
        truth = set(statement_by_id[m.statement_id].true_allocations)
        predicted = set(m.predicted_allocations)
        is_correct = predicted and predicted.issubset(truth)
        if not is_correct:
            continue
        if m.score_detail.get("token", 0) > 0:
            correct_with_token += 1
        else:
            correct_without_token += 1

    print(f"correct matches WITH token support:    {correct_with_token:,}")
    print(f"correct matches WITHOUT token support: {correct_without_token:,}")
    print()

    # Token is uniformly absent in this tier (exact already took the token-backed matches),
    # so it can't discriminate. The likely real signal is candidate competition: a correct
    # amount+date match tends to be the only viable candidate, while a coincidental twin is
    # one of several. Measure how many amount+date candidates each matched statement row
    # had, split by whether the resulting match was correct.
    candidates = scored._candidate_pairs(remaining_ledger, after_exact)
    statement_position = {s.row_id: i for i, s in enumerate(after_exact)}

    correct_by_competition = Counter()
    wrong_by_competition = Counter()
    for m in scored_matches:
        s_index = statement_position.get(m.statement_id)
        n_candidates = len(candidates.get(s_index, {}))
        bucket = "1 candidate" if n_candidates == 1 else (
            "2 to 3" if n_candidates <= 3 else "4 or more")
        truth = set(statement_by_id[m.statement_id].true_allocations)
        predicted = set(m.predicted_allocations)
        if predicted and predicted.issubset(truth):
            correct_by_competition[bucket] += 1
        else:
            wrong_by_competition[bucket] += 1

    print("candidate competition vs correctness (does uniqueness separate good from bad?):")
    for bucket in ["1 candidate", "2 to 3", "4 or more"]:
        c = correct_by_competition[bucket]
        w = wrong_by_competition[bucket]
        total = c + w
        rate = f"{c / total:.0%}" if total else "n/a"
        print(f"  {bucket}: {c:,} correct, {w:,} wrong  (precision {rate})")


if __name__ == "__main__":
    main()
