"""Match-rate is far too low, which points at candidate generation starving the scorer
rather than the scorer choosing badly. For statement rows that have a single true match,
this checks whether the correct ledger row even made it into the candidate set, and if
not, why: no shared token at all, or shared tokens filtered out by the distinctive-token
rule. Run with `python -m diagnostics.diagnose_candidates`.
"""

import re
from collections import Counter

from ingest import load
from matching.compare import _distinctive_tokens


def _all_tokens(row):
    text = f"{row.references} {row.attributes}".upper()
    return set(re.findall(r"[A-Z0-9]+", text))


def main():
    data = load()

    # Build a lookup from allocation key to the ledger rows that carry it, so we can find
    # the true ledger counterpart of a statement row.
    ledger_by_allocation = {}
    for l in data.ledger:
        ledger_by_allocation.setdefault(l.allocation, []).append(l)

    single = [s for s in data.statement if len(s.true_allocations) == 1]
    print(f"statement rows with exactly one true allocation: {len(single):,}")

    have_ledger = 0
    reasons = Counter()
    for s in single:
        truth = s.true_allocations[0]
        true_ledgers = ledger_by_allocation.get(truth, [])
        if not true_ledgers:
            reasons["true ledger row not in this sample"] += 1
            continue
        have_ledger += 1
        ledger = true_ledgers[0]

        # Would blocking connect them? Compare on distinctive tokens (what we use now) vs
        # all tokens (what we could use), and account/currency agreement.
        s_dist = _distinctive_tokens(s)
        l_dist = _distinctive_tokens(ledger)
        s_all = _all_tokens(s)
        l_all = _all_tokens(ledger)
        same_ac = ledger.account == s.account and ledger.currency == s.currency

        if not same_ac:
            reasons["account or currency differ"] += 1
        elif s_dist & l_dist:
            reasons["would be a candidate (shares distinctive token)"] += 1
        elif s_all & l_all:
            reasons["shares a token, but only ones the distinctive filter drops"] += 1
        else:
            reasons["shares no exact token at all"] += 1

    print(f"of those, true ledger row present in sample: {have_ledger:,}")
    print()
    print("why the true ledger row is or isn't a candidate:")
    for reason, count in reasons.most_common():
        print(f"  {reason}: {count:,}")
    print()

    # For the ones sharing no exact token, are the references actually similar (mangled)
    # or genuinely different? Show a few.
    print("examples sharing no exact token (is it mangling or real difference?):")
    shown = 0
    for s in single:
        if shown >= 5:
            break
        truth = s.true_allocations[0]
        true_ledgers = ledger_by_allocation.get(truth, [])
        if not true_ledgers:
            continue
        ledger = true_ledgers[0]
        if ledger.account == s.account and ledger.currency == s.currency and not (_all_tokens(s) & _all_tokens(ledger)):
            print(f"  statement refs: {s.references[:70]}")
            print(f"  ledger refs:    {ledger.references[:70]}")
            print()
            shown += 1


if __name__ == "__main__":
    main()
