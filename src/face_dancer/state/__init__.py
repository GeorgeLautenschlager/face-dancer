"""Dynamic state store — volatile, authoritative, code-written.

Holds current HP, conditions, resources, and position.
The model never writes here; every mutation is authored by code.
"""

from face_dancer.state.dynamic_state import DynamicState

__all__ = ["DynamicState"]
