# bank-to-book: write-up

## The workflow I chose, and why

I picked bank-statement-to-ledger reconciliation in the accounting vertical because it is a
problem where the obvious approach is wrong, and I wanted to show the work of finding that
out rather than the work of building something that just looks finished.

The workflow was diagnose first, build second. Before writing the matcher I wrote throwaway
scripts to interrogate the real data: how the two sides are structured, what the match
labels mean, and whether the thing I assumed would join transactions actually does. That
last question turned out to be the whole project. The intuitive design matches transactions
on their reference text. The data says that fails. For about three-quarters of true matches,
the bank reference and the ledger reference share nothing at all. So the design changed
before it was built. Amount, date and sign became the join, with reference codes as
corroboration where they exist. I kept the diagnostic scripts in the repo (under
`matching/diagnostics/`) because they are the argument for why the tool is shaped the way it
is, and they re-run against the data if you would rather check than trust me.

I used Claude as the engineering partner throughout. The honest version of that, including
the places it produced confident output I had to throw away, is in `AI_WORKFLOW.md`.

## What the tool does

It reads a bank statement and a ledger, matches lines through a deterministic cascade, and
sorts every line into one of three outcomes:

- **Auto-cleared.** Matched on amount, date and sign, and backed by a shared reference code.
  Committed without review.
- **Needs review.** Matched on amount and date alone, with no code to confirm it. Plausible,
  but unrelated transactions collide on round amounts, so a person looks.
- **Unmatched.** No candidate within tolerance. Routed as an open item.

It then writes a short briefing of the review queue: where the value is concentrated, likely
double-postings, a recurring reference code worth clearing in one batch, and any single
feed-day the exceptions pile up on. A local language model phrases that briefing, but every
fact in it is computed in code first. The model cannot invent a number or move a match.

Measured against the BenchRec labels on a 5,000-row sample, it auto-clears at 99.2%
precision, runs 91.3% precision across all matches, and recovers 69.7% of the lines that are
truly matchable. The auto-clear band is deliberately small. That gap between 99% and 91% is
the whole reason to separate what you trust from what you check. It is a dial between
precision and how much lands on a person's desk, not a number to push as high as it goes.

One thing I want to be straight about. When the scored tier gets a match wrong, that is
usually not a bug to fix. Those are transactions that are genuinely indistinguishable in the
data, same amount and date with no reference code, where any guess is a coin flip. The
honest move is to route them to a person, not to manufacture confidence. The ICAIF
organisers say as much: real reconciliation runs below 90% automation by design, and the
rest is manual. Matching everything would just mean matching some of it wrong.

## What breaks at real scale

The matching logic is the part I would keep. The rest needs work.

- **It assumes one statement and one ledger in one currency convention.** Real shops
  reconcile payables and receivables separately, across currencies, with different tolerance
  rules per account. The thresholds sitting in `config.py` would have to become per-account
  configuration.
- **It is a batch tool with no idempotency.** Run it twice and it reprocesses everything.
  Production reconciliation is incremental: new statement lines arrive daily and have to
  match against an open ledger without re-clearing what is already settled.
- **The briefing's six detectors are my judgment of what matters in cash reconciliation.**
  Concentration, double-postings, recurring codes, feed-day clusters. They are reasonable
  here and would miss the point on a different ledger. Insurance or a contractor's books
  have different tells. These are hand-built opinions, not a general anomaly model, and I
  would not pretend they transfer.
- **There is no fraud or control layer.** The tool flags what is unmatched. It does not ask
  whether an unmatched line is suspicious rather than just unrecorded, which is a different
  and harder problem it does not attempt.

## What I would build next with another week

The first thing would be incremental reconciliation with idempotency: match against an open
ledger, carry unresolved items forward, and never re-clear a settled line. That is the
change that would make this something you could actually run every day instead of a demo.

After that, per-account configuration for tolerances and matching rules. A single global
threshold is the most obvious thing that breaks the moment you have more than one real
account.

I would also A/B the local model. The briefing runs on llama3.1 right now; qwen2.5-7b scores
better on table reasoning in published benchmarks, and swapping it is a one-line config
change. That is worth measuring rather than assuming either way.

I would not spend the week adding detectors, though. More hand-built detectors is just more
of my opinion baked in. If anything the detectors should eventually be learned from labelled
reviewer decisions rather than written by me, but that is its own project and not a week of
work.

---
Built on the BenchRec cash dataset (ICAIF 2023, CC BY 4.0, by Operartis). The matching and
scoring are my own, an IDF-weighted token model with Hungarian assignment rather than an
off-the-shelf record-linkage library, because I wanted the logic legible and the tradeoffs
mine to defend. It runs entirely free and local: no paid APIs, no cloud, no Docker.
