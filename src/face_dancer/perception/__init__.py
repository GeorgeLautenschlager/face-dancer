"""Perception layer — session → character, epistemically scoped.

The character perceives only what it could plausibly know. The epistemic filter
sits between the host's world description and the character's context window.
"""

from face_dancer.perception.scene import Entity, PerceptionCheck, Scene

__all__ = ["Entity", "PerceptionCheck", "Scene"]
