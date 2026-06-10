"""Tests for model-call instrumentation."""

import pytest

from face_dancer.membrane.instrumentation import (
    ModelCall,
    ModelCallForbidden,
    NullModelGateway,
    model_calls_forbidden,
    record_model_call,
    recorded_model_calls,
)


def test_recorder_captures_calls_with_path_label() -> None:
    with recorded_model_calls() as rec:
        record_model_call("decision.tactical")
    assert rec.calls == [ModelCall(path="decision.tactical")]


def test_recorder_is_empty_when_path_makes_no_call() -> None:
    with recorded_model_calls() as rec:
        pass
    assert rec.calls == []


def test_recording_without_active_recorder_is_a_no_op() -> None:
    record_model_call("decision.tactical")  # must not raise


def test_forbidden_region_raises_with_reason_and_path() -> None:
    with (
        model_calls_forbidden("disposal is code-only"),
        pytest.raises(ModelCallForbidden) as excinfo,
    ):
        record_model_call("state.write")
    assert excinfo.value.reason == "disposal is code-only"
    assert excinfo.value.path == "state.write"


def test_forbidden_region_resets_after_block() -> None:
    with model_calls_forbidden("temporary"):
        pass
    with recorded_model_calls() as rec:
        record_model_call("free.path")
    assert rec.calls == [ModelCall(path="free.path")]


def test_nested_recorders_stay_isolated() -> None:
    with recorded_model_calls() as outer:
        with recorded_model_calls() as inner:
            record_model_call("inner.path")
        record_model_call("outer.path")
    assert inner.calls == [ModelCall(path="inner.path")]
    assert outer.calls == [ModelCall(path="outer.path")]


def test_forbidden_inside_recorder_raises_and_does_not_record() -> None:
    with (
        recorded_model_calls() as rec,
        model_calls_forbidden("inner block"),
        pytest.raises(ModelCallForbidden),
    ):
        record_model_call("some.path")
    assert rec.calls == []


def test_gateway_invoke_records_and_returns_canned_response() -> None:
    gateway = NullModelGateway(response="canned")
    with recorded_model_calls() as rec:
        result = gateway.invoke("decision.expressive", {"prompt": "hi"})
    assert result == "canned"
    assert rec.calls == [ModelCall(path="decision.expressive")]


def test_gateway_invoke_raises_inside_forbidden_region() -> None:
    gateway = NullModelGateway()
    with model_calls_forbidden("no model on this path"), pytest.raises(ModelCallForbidden):
        gateway.invoke("state.write", None)
