"""The membrane: propose/dispose seam, epistemic scope filter, model-call instrumentation.

Every hard boundary in Face Dancer is this one boundary — the model proposes,
code disposes, an epistemic filter sits between. Rider, perception, capability,
and decision each specialize these primitives rather than reinventing them.
"""

from face_dancer.membrane.instrumentation import (
    ModelCall,
    ModelCallForbidden,
    ModelCallRecorder,
    ModelGateway,
    NullModelGateway,
    model_calls_forbidden,
    record_model_call,
    recorded_model_calls,
)
from face_dancer.membrane.scope import PassThroughFilter, Scope, ScopeFilter
from face_dancer.membrane.seam import (
    Applied,
    Disposer,
    MembraneViolation,
    Proposal,
    dispose,
)

__all__ = [
    "Applied",
    "Disposer",
    "MembraneViolation",
    "ModelCall",
    "ModelCallForbidden",
    "ModelCallRecorder",
    "ModelGateway",
    "NullModelGateway",
    "PassThroughFilter",
    "Proposal",
    "Scope",
    "ScopeFilter",
    "dispose",
    "model_calls_forbidden",
    "record_model_call",
    "recorded_model_calls",
]
