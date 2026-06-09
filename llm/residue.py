"""Brief the reviewer on the queue: deterministic findings, phrased by the model.

The split is deliberate. insights.py decides what is worth saying, in code, and attaches the
real numbers and the rows each finding rests on. This module hands those findings to the
model with one job: put them into plain English a reviewer can act on, keeping the numbers,
adding no analysis. That is the one thing a small local model does well here; deciding what
matters is the thing it does badly, and that has already happened.

Because every finding is computed, the briefing degrades gracefully. If no endpoint is
reachable, or the model returns something that will not validate, we fall back to the
engine's own plain summaries, which are already specific. The reviewer always gets grounded
content; the model only ever improves the wording.

The schema (schema.py) has no numeric or allocation field, so the model cannot move a number
or invent a key. results.csv stays authoritative; this writes only to review.json.
"""

import json

from pydantic import ValidationError

import config
from llm import client, insights
from llm.schema import Briefing


SYSTEM_PROMPT = (
    "You are a senior reconciliation reviewer writing a short handoff note to the colleague "
    "who will work the review queue next. You are given findings that have already been "
    "computed from the data, each with its real numbers. Your only job is to phrase them in "
    "plain English, keeping every number exactly as given. Do not add findings, do not "
    "generalise, do not give generic advice. Every sentence must contain a specific number, "
    "date, or name from the findings. Avoid empty phrases such as \"it is essential to "
    "verify\", \"may indicate a need for further investigation\", \"it is important to note\", "
    "or \"plays a crucial role\". Reply with one JSON object and nothing else.\n\n"
    "Example of a BAD note (generic, restates nothing specific):\n"
    "  \"There are many unconfirmed transactions. It is essential to verify their accuracy.\"\n"
    "Example of a GOOD note (keeps the finding's numbers, says what to do):\n"
    "  \"The five largest lines hold 214,300 of the 487,000 queue total (44%); start there.\"\n\n"
    "Schema: {\"overview\": string, \"findings\": [{\"note\": string, \"action\": string}, ...]}."
)


def _user_prompt(findings, counts):
    """Hand the model the counts for its overview line and the pre-computed findings, in
    order, to phrase. The findings already carry their numbers, so the model is never asked
    to compute anything, only to read it back in plain words."""
    lines = [
        f"Queue counts: {counts['total']} lines total, "
        f"{counts['amber']} plausible but unconfirmed, {counts['red']} with no candidate.",
        "",
        "Findings to phrase, most important first:",
    ]
    for i, f in enumerate(findings, 1):
        lines.append(f"  {i}. {f.summary}")
    lines.append("")
    lines.append("Write the overview from the counts, then one note and action per finding.")
    return "\n".join(lines)


def _parse(content):
    """Pull the JSON object out of the reply and validate it against the schema."""
    start = content.find("{")
    end = content.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object in reply")
    return Briefing.model_validate_json(content[start:end + 1])


def _deterministic_briefing(findings, counts):
    """The fallback briefing, built with no model at all: the engine's own factual summaries,
    which are already specific. Used when the endpoint is unreachable or the model's reply
    will not validate, so the reviewer always gets grounded content."""
    overview = (
        f"{counts['total']} lines need review: {counts['amber']} matched on amount and date "
        f"but unconfirmed, {counts['red']} with no candidate found."
    )
    return {
        "overview": overview,
        "findings": [{"note": f.summary, "action": ""} for f in findings],
    }


def run(review_queue, statement_by_id):
    """Compute the findings, then phrase them with the model. Returns (briefing_dict_or_None,
    status). The findings are computed regardless, so even with no model reachable the
    reviewer gets a grounded briefing rather than nothing."""
    if not review_queue:
        return None, "review queue empty, no briefing needed"

    findings, counts = insights.profile(review_queue, statement_by_id)
    if not findings:
        # Nothing material stood out. Say that plainly rather than manufacture observations.
        briefing = {
            "overview": (
                f"{counts['total']} lines need review "
                f"({counts['amber']} unconfirmed, {counts['red']} with no candidate); "
                f"no single line, batch, or pattern stands out as material."
            ),
            "findings": [],
        }
        return briefing, "no material findings, wrote a plain queue overview"

    if not client.reachable():
        return _deterministic_briefing(findings, counts), (
            "LLM endpoint not reachable, wrote findings without phrasing "
            "(start Ollama or set a remote LLM_BASE_URL to have the model phrase them)"
        )

    user_prompt = _user_prompt(findings, counts)
    for _ in range(config.LLM_RETRY_ATTEMPTS):
        try:
            content = client.complete(SYSTEM_PROMPT, user_prompt, json_object=True)
            briefing = _parse(content).model_dump()
            return briefing, f"phrased {len(findings)} computed findings for the review queue"
        except (ValidationError, ValueError):
            continue
        except RuntimeError:
            break

    return _deterministic_briefing(findings, counts), (
        "LLM reply could not be validated, wrote findings without phrasing "
        "(deterministic findings stand)"
    )


def write_review(briefing, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(briefing, f, indent=2)
