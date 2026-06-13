"""The apply_delta executor: the single, model-free writer to dynamic state."""

from collections.abc import Callable
from typing import Any

from face_dancer.membrane import Applied, Proposal, dispose
from face_dancer.protocol import ApplyDelta, Delta, EffectOp
from face_dancer.state import DynamicState


class ApplyError(Exception):
    """An apply_delta could not be applied to dynamic state.

    Raised for a non-terminal op (scale/negate/grant_save/modify_roll), an unknown
    payload target, or a payload missing a required field.
    """


def _reduce(state: DynamicState, payload: dict[str, Any]) -> None:
    target = payload["target"]
    amount = payload["amount"]
    if target == "hp":
        state.hp -= amount
    elif target == "resources":
        key = payload["key"]
        state.resources[key] = state.resources.get(key, 0) - amount
    else:
        raise ApplyError(f"reduce: unknown target {target!r}")


def _replace(state: DynamicState, payload: dict[str, Any]) -> None:
    target = payload["target"]
    value = payload["value"]
    if target == "hp":
        state.hp = value
    elif target == "position":
        state.position = value
    elif target == "resources":
        state.resources[payload["key"]] = value
    else:
        raise ApplyError(f"replace: unknown target {target!r}")


_HANDLERS: dict[EffectOp, Callable[[DynamicState, dict[str, Any]], None]] = {
    EffectOp.REDUCE: _reduce,
    EffectOp.REPLACE: _replace,
}


def _apply(delta: Delta, state: DynamicState) -> DynamicState:
    handler = _HANDLERS.get(delta.op)
    if handler is None:
        raise ApplyError(f"{delta.op.value!r} is not a terminal state-write op")
    try:
        handler(state, delta.payload)
    except KeyError as exc:
        # The only KeyError source in the v0 handlers is the intended payload[...]
        # reads (state writes are attribute sets / dict __setitem__, which don't
        # raise KeyError). A future handler that *reads* from a dict must guard
        # its own lookups rather than let them masquerade as a missing field.
        raise ApplyError(f"{delta.op.value!r} payload missing field {exc}") from exc
    return state


def apply(message: ApplyDelta, state: DynamicState) -> Applied[DynamicState]:
    """Apply an authoritative apply_delta to dynamic state, model-free.

    The mutation runs inside the membrane's model-free region via ``dispose``;
    the returned ``Applied`` is proof a code-authored write committed.
    """
    proposal: Proposal[Delta] = Proposal(payload=message.delta, origin="session")
    return dispose(proposal, lambda d: _apply(d, state))
