"""Render the run as a single self-contained HTML page a non-technical owner can read.

summary.json and results.csv are the machine-readable record; this is the human one. It
draws three things a person cannot infer from a table at a glance: how the queue splits
across auto-cleared, review, and unmatched; how precision differs between the auto-cleared
band and the whole (which is the argument for banding at all); and how confident the scored
matches are. The LLM briefing, when present, sits at the top in plain words.

Everything is inline SVG and inline CSS in one file: no chart library, no web fonts, no
network. It opens from disk, which suits a local-first, free, replicable tool. The palette
and type are chosen to read as a quiet financial document, not a dashboard: the data is the
only thing that should draw the eye.
"""

import html

import config
from verify import GREEN, AMBER, RED


# A restrained financial-document palette: warm paper, ink text, and three status hues that
# read as their meaning (cleared / review / unmatched) without shouting.
PAPER = "#f6f4ef"
INK = "#1c1a17"
MUTED = "#6b6459"
RULE = "#d8d2c6"
GREEN_HUE = "#3f7d5e"
AMBER_HUE = "#c08a2d"
RED_HUE = "#a8553f"


def _bar_chart(rows, width=520, bar_height=34, gap=14):
    """Horizontal bars for the band split. Horizontal because the labels are words and the
    eye compares lengths left-aligned more easily than column heights."""
    total = sum(value for _, value, _ in rows) or 1
    height = len(rows) * (bar_height + gap)
    label_w = 120
    track_w = width - label_w - 70
    svg = [f'<svg viewBox="0 0 {width} {height}" role="img" width="100%">']
    for i, (label, value, color) in enumerate(rows):
        y = i * (bar_height + gap)
        bar_w = max(2, track_w * value / total)
        pct = 100 * value / total
        svg.append(
            f'<text x="0" y="{y + bar_height/2 + 5}" fill="{INK}" '
            f'font-size="15" font-weight="600">{html.escape(label)}</text>'
        )
        svg.append(
            f'<rect x="{label_w}" y="{y}" width="{bar_w:.1f}" height="{bar_height}" '
            f'rx="3" fill="{color}"/>'
        )
        svg.append(
            f'<text x="{label_w + bar_w + 10:.1f}" y="{y + bar_height/2 + 5}" '
            f'fill="{MUTED}" font-size="14">{value:,} ({pct:.0f}%)</text>'
        )
    svg.append("</svg>")
    return "".join(svg)


def _precision_chart(pairs, width=520, height=200):
    """Two precision bars, auto-cleared vs overall, on a shared 0-100 scale so the gap that
    justifies the banding is the thing the eye lands on."""
    pad_l, pad_b, pad_t = 60, 30, 10
    plot_w = width - pad_l - 20
    plot_h = height - pad_b - pad_t
    bar_w = plot_w / (len(pairs) * 2)
    svg = [f'<svg viewBox="0 0 {width} {height}" role="img" width="100%">']
    # gridlines at 0, 50, 100
    for gv in (0, 50, 100):
        y = pad_t + plot_h * (1 - gv / 100)
        svg.append(f'<line x1="{pad_l}" y1="{y:.1f}" x2="{width-20}" y2="{y:.1f}" stroke="{RULE}" stroke-width="1"/>')
        svg.append(f'<text x="{pad_l-10}" y="{y+4:.1f}" fill="{MUTED}" font-size="12" text-anchor="end">{gv}%</text>')
    for i, (label, value, color) in enumerate(pairs):
        x = pad_l + plot_w * (i + 0.5) / len(pairs) - bar_w / 2
        bar_h = plot_h * value
        y = pad_t + plot_h - bar_h
        svg.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{bar_h:.1f}" rx="3" fill="{color}"/>')
        # Place the value label above the bar, unless the bar is tall enough that the label
        # would collide with the top gridline, in which case drop it just inside the bar.
        if value > 0.9:
            label_y, fill = y + 22, PAPER
        else:
            label_y, fill = y - 8, INK
        svg.append(f'<text x="{x + bar_w/2:.1f}" y="{label_y:.1f}" fill="{fill}" font-size="14" font-weight="600" text-anchor="middle">{value*100:.1f}%</text>')
        svg.append(f'<text x="{x + bar_w/2:.1f}" y="{height-10}" fill="{MUTED}" font-size="13" text-anchor="middle">{html.escape(label)}</text>')
    svg.append("</svg>")
    return "".join(svg)


def _histogram(values, width=520, height=200, bins=10):
    """Confidence distribution of the scored matches, so a reviewer can see whether the
    amber pile clusters near certain or spreads thin."""
    if not values:
        return '<p class="empty">No scored matches to chart.</p>'
    counts = [0] * bins
    for v in values:
        idx = min(bins - 1, int(v * bins))
        counts[idx] += 1
    peak = max(counts) or 1
    pad_l, pad_b, pad_t = 40, 30, 10
    plot_w = width - pad_l - 20
    plot_h = height - pad_b - pad_t
    bar_w = plot_w / bins
    svg = [f'<svg viewBox="0 0 {width} {height}" role="img" width="100%">']
    for i, c in enumerate(counts):
        bar_h = plot_h * c / peak
        x = pad_l + i * bar_w
        y = pad_t + plot_h - bar_h
        svg.append(f'<rect x="{x+2:.1f}" y="{y:.1f}" width="{bar_w-4:.1f}" height="{bar_h:.1f}" rx="2" fill="{AMBER_HUE}"/>')
        if c:
            svg.append(f'<text x="{x+bar_w/2:.1f}" y="{y-5:.1f}" fill="{MUTED}" font-size="11" text-anchor="middle">{c}</text>')
    # x-axis labels at 0.0, 0.5, 1.0 of the confidence range
    for frac, lab in ((0, "0.0"), (0.5, "0.5"), (1.0, "1.0")):
        x = pad_l + plot_w * frac
        svg.append(f'<text x="{x:.1f}" y="{height-10}" fill="{MUTED}" font-size="12" text-anchor="middle">{lab}</text>')
    svg.append("</svg>")
    return "".join(svg)


def _briefing_block(briefing):
    if not briefing:
        return (
            '<p class="brief-empty">No review-queue briefing for this run. The deterministic '
            'report below stands on its own; start the local model to add a plain-language '
            'briefing.</p>'
        )
    parts = [f'<p class="brief-overview">{html.escape(briefing.get("overview", ""))}</p>']
    findings = briefing.get("findings") or []
    if findings:
        items = []
        for f in findings:
            note = html.escape(f.get("note", ""))
            action = f.get("action", "")
            if action:
                note += f' <span class="brief-action">{html.escape(action)}</span>'
            items.append(f"<li>{note}</li>")
        parts.append(f'<ul class="brief-list">{"".join(items)}</ul>')
    return "".join(parts)


def write_report(decisions, summary, briefing, path):
    """Assemble the page from the same decisions and summary the pipeline already computed."""
    m = summary.get("measured", {})
    band = summary["by_band"]

    band_rows = [
        ("Auto-cleared", band[GREEN], GREEN_HUE),
        ("Needs review", band[AMBER], AMBER_HUE),
        ("Unmatched", band[RED], RED_HUE),
    ]
    precision_pairs = []
    if m.get("green_precision") is not None:
        precision_pairs.append(("Auto-cleared", m["green_precision"], GREEN_HUE))
    if m.get("precision") is not None:
        precision_pairs.append(("All matched", m["precision"], MUTED))

    scored_confidences = [
        d.confidence for d in decisions if d.tier == "scored" and d.confidence > 0
    ]

    headline_match = f'{m["match_rate"]*100:.0f}%' if m.get("match_rate") is not None else "n/a"
    headline_green = f'{m["green_precision"]*100:.1f}%' if m.get("green_precision") is not None else "n/a"

    page = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Reconciliation report</title>
<style>
  :root {{ color-scheme: light; }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; background: {PAPER}; color: {INK};
    font-family: "Iowan Old Style", "Palatino Linotype", Georgia, serif;
    line-height: 1.5; padding: 48px 24px;
  }}
  .sheet {{ max-width: 760px; margin: 0 auto; }}
  .eyebrow {{
    font-family: ui-monospace, "SF Mono", Menlo, monospace;
    font-size: 12px; letter-spacing: 0.14em; text-transform: uppercase;
    color: {MUTED}; margin: 0 0 6px;
  }}
  h1 {{ font-size: 30px; font-weight: 600; margin: 0 0 4px; letter-spacing: -0.01em; }}
  .sub {{ color: {MUTED}; margin: 0 0 32px; font-size: 15px; }}
  .headline {{
    display: flex; gap: 40px; padding: 22px 0; margin: 0 0 8px;
    border-top: 1px solid {RULE}; border-bottom: 1px solid {RULE};
  }}
  .headline div {{ flex: 1; }}
  .headline .num {{ font-size: 34px; font-weight: 600; letter-spacing: -0.02em; }}
  .headline .lab {{ font-size: 13px; color: {MUTED}; }}
  section {{ margin: 34px 0; }}
  h2 {{
    font-family: ui-monospace, "SF Mono", Menlo, monospace;
    font-size: 12px; letter-spacing: 0.12em; text-transform: uppercase;
    color: {MUTED}; font-weight: 600; margin: 0 0 4px;
  }}
  .note {{ font-size: 14px; color: {MUTED}; margin: 0 0 16px; max-width: 60ch; }}
  .brief-overview {{ font-size: 17px; margin: 0 0 12px; }}
  .brief-list {{ margin: 0; padding-left: 20px; color: {INK}; }}
  .brief-list li {{ margin: 4px 0; font-size: 15px; }}
  .brief-action {{ color: {MUTED}; font-style: italic; }}
  .brief-empty, .empty {{ color: {MUTED}; font-style: italic; font-size: 15px; }}
  footer {{
    margin-top: 40px; padding-top: 16px; border-top: 1px solid {RULE};
    font-size: 12px; color: {MUTED};
    font-family: ui-monospace, "SF Mono", Menlo, monospace;
  }}
</style>
</head>
<body>
<div class="sheet">
  <p class="eyebrow">Bank-to-books reconciliation</p>
  <h1>Run report</h1>
  <p class="sub">{summary['total_statement_rows']:,} statement lines processed against the ledger.</p>

  <div class="headline">
    <div>
      <div class="num">{headline_green}</div>
      <div class="lab">precision on auto-cleared lines</div>
    </div>
    <div>
      <div class="num">{headline_match}</div>
      <div class="lab">of truly matchable lines recovered</div>
    </div>
    <div>
      <div class="num">{band[GREEN]:,}</div>
      <div class="lab">cleared without review</div>
    </div>
  </div>

  <section>
    <h2>Briefing</h2>
    {_briefing_block(briefing)}
  </section>

  <section>
    <h2>Where the lines went</h2>
    <p class="note">Every statement line lands in one of three places: cleared automatically,
      sent to a person to review, or left unmatched. The tool only auto-clears what it can
      corroborate, and routes the rest rather than guessing.</p>
    {_bar_chart(band_rows)}
  </section>

  <section>
    <h2>Why the split is worth it</h2>
    <p class="note">Auto-cleared lines are far more accurate than matched lines overall. That
      gap is the point of separating them: the confident matches can be trusted, the
      uncertain ones go to review instead of polluting the books.</p>
    {_precision_chart(precision_pairs)}
  </section>

  <section>
    <h2>Confidence of review-queue matches</h2>
    <p class="note">For lines matched on amount and date alone, how strong was the match
      score? A pile near the right is safer to confirm quickly; a spread means more genuine
      judgement calls.</p>
    {_histogram(scored_confidences)}
  </section>

  <footer>
    Generated by bank-to-book. Figures measured against the BenchRec (ICAIF 2023) labels.
    results.csv holds every line-level decision; summary.json holds the exact figures.
  </footer>
</div>
</body>
</html>"""

    with open(path, "w", encoding="utf-8") as f:
        f.write(page)