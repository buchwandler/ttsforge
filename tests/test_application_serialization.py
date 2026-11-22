from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import pytest

from ttsforge.application import (
    InputValidationError,
    WorkflowFailureError,
    error_view,
    json_value,
)


class State(Enum):
    READY = "ready"


@dataclass(frozen=True)
class ExampleDTO:
    path: Path
    state: State
    values: tuple[int, None]


def test_json_value_serializes_dataclasses_paths_enums_tuples_and_mappings() -> None:
    value = ExampleDTO(Path("/books/book.epub"), State.READY, (3, None))

    assert json_value(value) == {
        "path": "/books/book.epub",
        "state": "ready",
        "values": [3, None],
    }
    assert json.loads(json.dumps(json_value(value))) == {
        "path": "/books/book.epub",
        "state": "ready",
        "values": [3, None],
    }


def test_json_value_rejects_unknown_values_and_non_string_mapping_keys() -> None:
    with pytest.raises(TypeError, match="Unsupported JSON value type"):
        json_value(object())
    with pytest.raises(TypeError, match="keys must be strings"):
        json_value({1: "value"})


def test_error_view_preserves_structured_application_error_fields() -> None:
    error = WorkflowFailureError(
        "Preflight failed",
        category="workflow preflight failure",
        code="audioexport_unavailable",
        stage="export",
        package="audioexport",
        selector="5-17",
        details={"available": False},
    )

    assert error_view(error).to_dict() == {
        "type": "WorkflowFailureError",
        "message": "Preflight failed",
        "category": "workflow preflight failure",
        "code": "audioexport_unavailable",
        "stage": "export",
        "package": "audioexport",
        "selector": "5-17",
        "details": {"available": False},
    }


def test_error_view_keeps_expected_message_and_hides_unexpected_message() -> None:
    assert error_view(InputValidationError("Bad source")).message == "Bad source"
    unexpected = error_view(RuntimeError("private traceback detail"))
    assert unexpected.type == "RuntimeError"
    assert unexpected.message == "An unexpected error occurred."
