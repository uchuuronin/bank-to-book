"""The shape the LLM must return, so its reply is validated rather than trusted.

The model is given findings that the deterministic insight engine has already selected and
backed with numbers, and asked only to phrase them for a reviewer. It returns one overview
line and one phrased note per finding. It never returns an amount, a count, or an allocation
key: those come from the engine, the schema has no field for them, so a weak model has
nothing to fabricate into the ledger. Keeping the schema small and every field described is
what makes a local model fill it reliably under constrained decoding.
"""

from pydantic import BaseModel, Field


class PhrasedFinding(BaseModel):
    """One finding, put into plain words. `note` must restate the specific finding it was
    given (with its numbers), not generalise away from it; `action` is what the reviewer
    should do about it, in one short clause."""

    note: str = Field(
        ...,
        max_length=300,
        description="One plain sentence stating this specific finding, keeping its actual "
                    "numbers, dates, or names. No hedging, no generic advice.",
    )
    action: str = Field(
        ...,
        max_length=160,
        description="One short clause: what the reviewer should do about this finding first.",
    )


class Briefing(BaseModel):
    """The whole briefing: a one-line overview of the queue, then the phrased findings in the
    order they were given (already ranked by materiality)."""

    overview: str = Field(
        ...,
        max_length=300,
        description="One sentence summarising the size and make-up of the review queue, "
                    "using the counts provided. No advice in this line.",
    )
    findings: list[PhrasedFinding] = Field(default_factory=list, max_length=6)
