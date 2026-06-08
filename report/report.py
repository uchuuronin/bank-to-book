"""Write the two outputs a person actually reads.

results.csv has one row per decision, with the columns a reviewer needs to understand and
check it: the statement row, the band, what it was matched to, the confidence, the tier
that decided it, and a plain reason. summary.json has the counts, keyed by the same band
and tier names so a number in the summary traces straight back to the rows that produced
it. No drawn tables, no decoration: the data is the report.
"""

import csv
import json

import config
from verify import GREEN, AMBER, RED


def write_results(decisions, path):
    """One decision per row. Columns are self-explanatory so the CSV reads as a CSV."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "statement_id", "band", "tier", "confidence",
            "matched_ledger_ids", "predicted_allocations", "reason",
        ])
        for d in decisions:
            writer.writerow([
                d.statement_id,
                d.band,
                d.tier,
                f"{d.confidence:.3f}",
                " ".join(d.ledger_ids),
                " ".join(d.predicted_allocations),
                d.reason,
            ])


def build_summary(decisions, scored_truth=None):
    """Counts keyed by band and tier, plus measured accuracy when truth is supplied. The
    keys match the values in results.csv so the summary and the rows line up."""
    by_band = {GREEN: 0, AMBER: 0, RED: 0}
    by_tier = {}
    for d in decisions:
        by_band[d.band] += 1
        by_tier[d.tier] = by_tier.get(d.tier, 0) + 1

    summary = {
        "total_statement_rows": len(decisions),
        "by_band": by_band,
        "by_tier": by_tier,
        "auto_matched_green": by_band[GREEN],
        "routed_to_review": by_band[AMBER] + by_band[RED],
    }
    if scored_truth is not None:
        summary["measured"] = scored_truth
    return summary


def write_summary(summary, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
