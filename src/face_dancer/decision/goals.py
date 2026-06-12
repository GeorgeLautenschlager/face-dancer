"""The Goals model: goal inputs biasing the decision at three timescales."""

from pydantic import BaseModel, Field


class Goals(BaseModel):
    """Goals biasing the decision at three timescales.

    ``persistent_drives`` come from persona; ``situational_objectives`` are
    scene-level and host-supplied (empty = the #6 fallback: no inference, bias on
    drives + tactical intent only); ``tactical_intent`` is the per-turn aim. Prose
    the decision policy reads.
    """

    persistent_drives: list[str] = Field(default_factory=list)
    situational_objectives: list[str] = Field(default_factory=list)
    tactical_intent: str | None = None
