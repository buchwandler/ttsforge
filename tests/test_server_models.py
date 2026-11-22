from __future__ import annotations

import pytest

pytest.importorskip("pydantic")

from pydantic import ValidationError

from ttsforge.server.models import AudiobookRequestModel, JobSubmissionModel


def test_job_request_accepts_json_engine_options_and_rejects_unknown_fields() -> None:
    request = AudiobookRequestModel(
        source="/books/book.epub",
        engine_options={"seed": 7, "metadata": {"tags": ["a", "b"]}},
    )
    submission = JobSubmissionModel(
        request=request,
        explicit_fields=["engine", "voice"],
    )

    assert submission.request.engine_options["metadata"] == {"tags": ["a", "b"]}
    assert submission.explicit_fields == ["engine", "voice"]
    with pytest.raises(ValidationError):
        AudiobookRequestModel(source="/books/book.epub", unexpected=True)


def test_request_model_uses_strict_json_field_types() -> None:
    with pytest.raises(ValidationError):
        AudiobookRequestModel(source="/books/book.epub", offline="false")
