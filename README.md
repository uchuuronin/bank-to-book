# bank-to-book

A command-line reconciliation tool that matches bank-statement lines against ledger
entries, decides which matches are safe to clear automatically, and hands the rest to a
person with a plain-English briefing of what needs attention.

It is built for the case real reconciliation actually lives in: there is no shared
transaction ID across the two sides, the reference text on a bank line rarely matches the
reference on its ledger entry, and a meaningful share of lines have no match at all. The
tool leans on the one signal that does join the two sides (amount, date and sign),
corroborates with reference codes where they exist, and refuses to guess when they don't.

Built against the BenchRec cash dataset (ICAIF 2023), which ships real labels, so every
run reports its own match rate and precision rather than asking you to take its word.

## What it does

Each statement line ends up in one of three places:

- **Auto-cleared** — matched on amount, date and sign, and corroborated by a shared
  reference code. High confidence, committed without review.
- **Needs review** — matched on amount and date alone, with no reference code to confirm
  it. Plausible, but unrelated transactions collide on round amounts, so these go to a
  human.
- **Unmatched** — no candidate within tolerance. Routed to review as an open item.

It writes four things to `report/output/`: `results.csv` (one decision per line),
`summary.json` (the counts and measured accuracy), `report.html` (a readable one-page
report with charts), and `review.json` (the review-queue briefing).

On the sample (5,000 rows): ~99% precision on what it auto-clears, ~91% precision overall,
~70% of truly matchable lines recovered. The auto-cleared band is deliberately small and
conservative — that gap between 99% and 91% is the whole argument for separating what you
trust from what you check.

## Setup

Python 3.10 or newer.

```bash
git clone https://github.com/uchuuronin/bank-to-book.git
cd bank-to-book
pip install -r requirements.txt
```

Then download the BenchRec cash dataset and drop it in `data/`. It is not in the repo
(it's large, and not mine to redistribute). Get it from Kaggle:

```
https://www.kaggle.com/datasets/operartis/benchrec
```

You need `BenchRec_cash_v1.0_train.csv` in `data/`. The eval and solution splits are
optional; the tool builds and measures on train.

## Running it

```bash
python pipeline.py
```

That runs the whole thing and prints what happened. Outputs land in `report/output/`. Open
`report.html` in any browser to see the readable version.

By default it processes a 5,000-row sample for fast iteration. For the full file, set
`SAMPLE_ROWS = None` in `config.py`.

### The plain-English briefing (optional)

The review-queue briefing in `review.json` and at the top of `report.html` is written by a
local language model. It is the only model step, it runs after everything deterministic is
already decided, and it can't change a number or a match — it only phrases findings the
tool computed itself. If no model is running, the tool falls back to its own plain
summaries and the briefing still has real content.

To enable the model, install [Ollama](https://ollama.com) and pull a model:

```bash
ollama pull llama3.1
```

Ollama serves on `localhost:11434` by default, which is where the tool looks. Nothing
leaves your machine, and there is no API key or cost. To point at a hosted
OpenAI-compatible endpoint instead, set `LLM_BASE_URL`, `LLM_MODEL` and `LLM_API_KEY` as
environment variables — the code doesn't change.

## How it's organised

```
config.py            paths, column names, tolerances, model settings — all settings live here
pipeline.py          runs the whole thing end to end
ingest/              read BenchRec into clean typed records (loader, records, checks)
matching/            the deterministic cascade
  compare.py           shared comparison rules (amount/date/sign, distinctive tokens)
  exact.py             high-confidence pass: amount + date + shared reference code
  scored.py            amount-and-date matching with global (Hungarian) resolution
  score.py             blends amount, date and a reference-token bonus into one score
  token_weights.py     IDF model: which reference codes actually identify a transaction
  diagnostics/         the scripts used to interrogate the data before building
verify/              band each match green / amber / red and route the uncertain ones
report/              results.csv + summary.json (report.py), report.html (html_report.py)
llm/                 the briefing tier
  insights.py          computes the findings (the content selection — done in code)
  residue.py           hands findings to the model to phrase; falls back if none
  schema.py            the shape the model must return
  client.py            thin OpenAI-compatible client
```

Run order: `ingest` → `matching` (exact, then scored) → `verify` → `report` → `llm`.

## Notes

- 100% free and local. No paid APIs, no cloud, no Docker — a plain Python CLI you can run
  offline.
- `data/` and the model output in `report/output/` are gitignored; the tracked outputs are
  there as `.gitkeep` placeholders.
- The diagnostics under `matching/diagnostics/` are kept on purpose. They are how the
  design decisions got made, and they re-run against the data if you want to check the
  reasoning rather than trust it.
