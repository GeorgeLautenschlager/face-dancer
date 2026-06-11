"""The shared delta shape: one effect a propose/apply message carries.

A ``Delta`` is exactly one operation: a single ``op`` drawn from the closed
``EffectOp`` vocabulary, the tag-set it applies under (open ``frozenset[str]`` —
the rider matches on op + tag-set), and an open ``payload``. The per-op payload
schemas (what ``reduce`` carries vs. ``grant_save``) belong to the executor that
applies them; here the payload is carried, not asserted.
"""

from typing import Any

from pydantic import BaseModel, Field

from face_dancer.protocol.vocabulary import EffectOp


class Delta(BaseModel):
    """One effect: a single op, the tag-set it applies under, and its payload."""

    op: EffectOp
    tags: frozenset[str] = frozenset()
    payload: dict[str, Any] = Field(default_factory=dict)
