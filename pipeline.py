"""Run the whole reconciliation end to end.

Loads the data, runs the deterministic cascade (exact pre-pass, then scored matching with
global resolution), bands every decision and routes the uncertain ones to review, writes
the results and summary, and prints what happened. Because the dataset carries real
labels, it also measures match rate and precision against the truth using the benchmark's
subset rule.

The LLM tier is deliberately not on the critical path: the deterministic cascade is the
tool. Run with `python pipeline.py`.
"""

import sys

import config
from ingest import load
from matching import exact, scored
from matching.token_weights import TokenWeights
from verify import run as verify_run, GREEN, AMBER, RED
from report import write_results, build_summary, write_summary, write_report
import llm


def _is_correct(predicted, truth):
    """The benchmark's rule: a prediction is correct if it is a non-empty subset of the
    true allocation set."""
    predicted, truth = set(predicted), set(truth)
    return bool(predicted) and predicted.issubset(truth)


def _measure(decisions, statement_by_id):
    """Match rate and precision against the real labels, plus a precision read on the
    auto-matched green band alone, since that is what the tool would commit without review."""
    truly_matchable = sum(1 for s in statement_by_id.values() if s.true_allocations)

    claimed = [d for d in decisions if d.predicted_allocations]
    correct = sum(
        1 for d in claimed
        if _is_correct(d.predicted_allocations, statement_by_id[d.statement_id].true_allocations)
    )
    green = [d for d in claimed if d.band == GREEN]
    green_correct = sum(
        1 for d in green
        if _is_correct(d.predicted_allocations, statement_by_id[d.statement_id].true_allocations)
    )

    return {
        "truly_matchable": truly_matchable,
        "claimed": len(claimed),
        "correct": correct,
        "precision": round(correct / len(claimed), 4) if claimed else None,
        "match_rate": round(correct / truly_matchable, 4) if truly_matchable else None,
        "green_claimed": len(green),
        "green_correct": green_correct,
        "green_precision": round(green_correct / len(green), 4) if green else None,
    }


def main():
    data = load()
    statement_by_id = {s.row_id: s for s in data.statement}
    weights = TokenWeights(data.ledger + data.statement)

    exact_matches, after_exact, used = exact.run(data.ledger, data.statement)
    remaining_ledger = [l for l in data.ledger if l.row_id not in used]
    scored_matches, unmatched, _ = scored.run(remaining_ledger, after_exact, weights)

    all_matches = exact_matches + scored_matches
    decisions, review_queue = verify_run(all_matches, unmatched)

    measured = _measure(decisions, statement_by_id)
    summary = build_summary(decisions, scored_truth=measured)

    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    results_path = config.OUTPUT_DIR / "results.csv"
    summary_path = config.OUTPUT_DIR / "summary.json"
    write_results(decisions, results_path)
    write_summary(summary, summary_path)

    # LLM residue tier: brief the reviewer on the queue in plain English. Runs only after
    # the deterministic outputs above are on disk, so it can never block or alter them. With
    # no endpoint reachable it does nothing but report that it skipped.
    briefing, llm_status = llm.run(review_queue, statement_by_id)
    review_path = config.OUTPUT_DIR / "review.json"
    if briefing:
        llm.write_review(briefing, review_path)

    # The human-readable report: same numbers as summary.json, rendered as a single
    # self-contained HTML page with the briefing at the top. Built last so it can include
    # the briefing when one was produced.
    report_path = config.OUTPUT_DIR / "report.html"
    write_report(decisions, summary, briefing, report_path)

    print(f"statement rows processed:  {len(data.statement):,}")
    print(f"  quarantined at ingest:   {len(data.quarantined):,}")
    print()
    print(f"auto-matched (green):      {summary['by_band'][GREEN]:,}")
    print(f"routed to review (amber):  {summary['by_band'][AMBER]:,}")
    print(f"unmatched (red):           {summary['by_band'][RED]:,}")
    print()
    print("matched by tier:")
    for tier, count in summary["by_tier"].items():
        if tier != "unmatched":
            print(f"  {tier}: {count:,}")
    print()
    if measured["precision"] is not None:
        print(f"overall precision:   {measured['precision']:.1%}  "
              f"({measured['correct']:,} of {measured['claimed']:,} claimed)")
    if measured["green_precision"] is not None:
        print(f"green-band precision: {measured['green_precision']:.1%}  "
              f"({measured['green_correct']:,} of {measured['green_claimed']:,} auto-matched)")
    if measured["match_rate"] is not None:
        print(f"match rate:          {measured['match_rate']:.1%}  "
              f"({measured['correct']:,} of {measured['truly_matchable']:,} truly matchable)")
    print()
    print(f"LLM residue tier: {llm_status}")
    outputs = f"{results_path.name}, {summary_path.name}, {report_path.name}"
    if briefing:
        outputs += f", {review_path.name}"
    print(f"wrote {outputs}")

    # Exit code in the spirit of a CI-ready tool: 0 if nothing needs review, 1 if the
    # review queue is non-empty, 2 reserved for errors (raised exceptions exit non-zero
    # on their own).
    return 1 if review_queue else 0


if __name__ == "__main__":
    sys.exit(main())