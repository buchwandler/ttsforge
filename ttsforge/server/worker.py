"""Isolated JSONL conversion worker process."""

from __future__ import annotations

import json
import logging
import os
import sys
import traceback
from collections.abc import Callable
from contextlib import redirect_stdout
from typing import Protocol, TextIO

from ..application import (
    AudiobookRequest,
    InputOverrides,
    InputValidationError,
    error_view,
    json_value,
)
from ..application.conversion import PreparedConversion
from ..application.events import ApplicationEvent
from ..application.models import ConversionResultView
from .models import JobSubmissionModel
from .requests import application_overrides, application_request


class ConversionRunner(Protocol):
    def prepare(
        self, request: AudiobookRequest, overrides: InputOverrides
    ) -> PreparedConversion: ...

    def execute(
        self,
        prepared: PreparedConversion,
        *,
        on_progress: Callable[[ApplicationEvent], None] | None = None,
    ) -> ConversionResultView: ...


class WorkerServices(Protocol):
    @property
    def conversion(self) -> ConversionRunner: ...


def main() -> int:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO)
    stdout_fd = sys.stdout.fileno()
    protocol_fd = os.dup(stdout_fd)
    os.dup2(sys.stderr.fileno(), stdout_fd)
    with os.fdopen(protocol_fd, "w", encoding="utf-8", buffering=1) as protocol:
        return run_worker(sys.stdin.read(), protocol, sys.stderr)


def run_worker(
    input_text: str,
    protocol_stream: TextIO,
    diagnostics_stream: TextIO,
    *,
    service_factory: Callable[[], WorkerServices] | None = None,
) -> int:
    debug = False
    try:
        payload = json.loads(input_text)
        if not isinstance(payload, dict):
            raise InputValidationError("Worker input must be a JSON object.")
        debug_value = payload.pop("debug", False)
        if not isinstance(debug_value, bool):
            raise InputValidationError("Worker debug setting must be boolean.")
        debug = debug_value
        _emit(protocol_stream, {"type": "job.state", "state": "preparing"})
        with redirect_stdout(diagnostics_stream):
            submission = JobSubmissionModel.model_validate(payload)
            request = application_request(submission.request)
            overrides = application_overrides(submission.explicit_fields)
            services = (service_factory or _application_services)()
            prepared = services.conversion.prepare(request, overrides)
            _emit(
                protocol_stream,
                {
                    "type": "job.prepared",
                    "project": str(prepared.preparation.paths.root),
                    "output": (
                        str(prepared.resolved.request.output)
                        if prepared.resolved.request.output is not None
                        else None
                    ),
                },
            )
            _emit(protocol_stream, {"type": "job.state", "state": "running"})
            result = services.conversion.execute(
                prepared,
                on_progress=lambda event: _emit(
                    protocol_stream,
                    {"type": "workflow.event", "event": json_value(event)},
                ),
            )
            _emit(
                protocol_stream,
                {"type": "job.result", "result": json_value(result)},
            )
        return 0
    except Exception as error:
        diagnostics_stream.write(f"Conversion worker failed: {type(error).__name__}\n")
        if debug:
            traceback.print_exc(file=diagnostics_stream)
        try:
            _emit(
                protocol_stream,
                {"type": "job.error", "error": json_value(error_view(error))},
            )
        except OSError:
            return 1
        return 1


def _application_services() -> WorkerServices:
    from .app import _application_services as create_services

    return create_services()


def _emit(stream: TextIO, message: object) -> None:
    payload = json.dumps(
        json_value(message),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )
    stream.write(payload + "\n")
    stream.flush()


if __name__ == "__main__":
    raise SystemExit(main())
