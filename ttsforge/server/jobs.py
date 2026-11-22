"""In-memory bounded-progress job records and isolated worker supervision."""

from __future__ import annotations

import json
import logging
import math
import os
import signal
import subprocess
import sys
import threading
import uuid
from collections import deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from ..application.errors_view import ErrorView
from ..application.events import ApplicationEvent
from ..application.models import (
    AudiobookRequest,
    ConversionResultView,
    InputOverrides,
)
from ..application.serialization import JsonValue, json_value

_LOG = logging.getLogger(__name__)
_MAX_PROTOCOL_LINE_BYTES = 1024 * 1024


class JobState(str, Enum):
    QUEUED = "queued"
    PREPARING = "preparing"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


_TERMINAL_STATES = frozenset({JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED})


@dataclass(frozen=True, slots=True)
class JobEventRecord:
    sequence: int
    timestamp: str
    event: dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class JobEventPage:
    next: int
    events: tuple[JobEventRecord, ...]


@dataclass(frozen=True, slots=True)
class JobRecord:
    id: str
    state: JobState
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    request: AudiobookRequest
    project: Path | None
    output: Path | None
    progress: ApplicationEvent | None
    result: ConversionResultView | None
    error: ErrorView | None
    event_sequence: int
    event_history: tuple[JobEventRecord, ...]


@dataclass(slots=True)
class _MutableJobRecord:
    id: str
    state: JobState
    created_at: datetime
    request: AudiobookRequest
    payload: str
    project: Path | None
    output: Path | None
    event_history: deque[JobEventRecord]
    started_at: datetime | None = None
    finished_at: datetime | None = None
    progress: ApplicationEvent | None = None
    result: ConversionResultView | None = None
    error: ErrorView | None = None
    event_sequence: int = 0
    cancellation_requested: bool = False


class _WorkerProtocolError(Exception):
    pass


class JobManager:
    """Schedule one or a small bounded number of subprocess workers."""

    def __init__(
        self,
        *,
        max_active_jobs: int = 1,
        event_history_limit: int = 1000,
        cancel_grace_seconds: float = 2.0,
        debug: bool = False,
        worker_command: Sequence[str] | None = None,
    ) -> None:
        if max_active_jobs < 1 or event_history_limit < 1 or cancel_grace_seconds < 0:
            raise ValueError("Job manager limits must be positive.")
        if worker_command is not None and not worker_command:
            raise ValueError("Worker command cannot be empty.")

        self._max_active_jobs = max_active_jobs
        self._event_history_limit = event_history_limit
        self._cancel_grace_seconds = cancel_grace_seconds
        self._debug = debug
        self._worker_command = tuple(
            worker_command or (sys.executable, "-m", "ttsforge.server.worker")
        )
        self._condition = threading.Condition()
        self._jobs: dict[str, _MutableJobRecord] = {}
        self._queue: deque[str] = deque()
        self._active_jobs: set[str] = set()
        self._processes: dict[str, subprocess.Popen[str]] = {}
        self._runner_threads: set[threading.Thread] = set()
        self._shutdown = False
        self._scheduler_started = False
        self._scheduler = threading.Thread(
            target=self._schedule,
            name="ttsforge-job-scheduler",
            daemon=True,
        )

    def submit(
        self, request: AudiobookRequest, overrides: InputOverrides | None = None
    ) -> JobRecord:
        selected_overrides = overrides or InputOverrides()
        request_json = json_value(request)
        payload = json.dumps(
            {
                "request": request_json,
                "explicit_fields": sorted(selected_overrides.fields),
                "debug": self._debug,
            },
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )
        now = datetime.now(timezone.utc)
        job_id = _new_job_id()
        record = _MutableJobRecord(
            id=job_id,
            state=JobState.QUEUED,
            created_at=now,
            request=request,
            payload=payload,
            project=request.project or request.source.with_suffix(".ttsforge"),
            output=request.output or request.source.with_suffix(".m4b"),
            event_history=deque(maxlen=self._event_history_limit),
        )
        with self._condition:
            if self._shutdown:
                raise RuntimeError("Job manager is shutting down.")
            self._jobs[job_id] = record
            self._queue.append(job_id)
            self._append_event(
                record,
                {"type": "job.state", "state": JobState.QUEUED.value},
            )
            if not self._scheduler_started:
                self._scheduler_started = True
                self._scheduler.start()
            self._condition.notify_all()
            return self._snapshot(record)

    def get(self, job_id: str) -> JobRecord:
        with self._condition:
            return self._snapshot(self._require_job(job_id))

    def events(self, job_id: str, *, after: int = 0) -> JobEventPage:
        if after < 0:
            raise ValueError("Event cursor must be non-negative.")
        with self._condition:
            record = self._require_job(job_id)
            events = tuple(
                item for item in record.event_history if item.sequence > after
            )
            return JobEventPage(record.event_sequence, events)

    def cancel(self, job_id: str) -> JobRecord:
        process: subprocess.Popen[str] | None = None
        with self._condition:
            record = self._require_job(job_id)
            if record.state in _TERMINAL_STATES:
                return self._snapshot(record)
            record.cancellation_requested = True
            if record.state is JobState.QUEUED:
                try:
                    self._queue.remove(job_id)
                except ValueError:
                    pass
                self._transition(record, JobState.CANCELLED)
                self._condition.notify_all()
                return self._snapshot(record)
            process = self._processes.get(job_id)

        if process is not None:
            _terminate_process_tree(process, self._cancel_grace_seconds)
        with self._condition:
            return self._snapshot(self._require_job(job_id))

    def shutdown(self, *, wait: bool = True) -> None:
        processes: tuple[subprocess.Popen[str], ...]
        with self._condition:
            if not self._shutdown:
                self._shutdown = True
                for job_id in tuple(self._queue):
                    record = self._jobs[job_id]
                    record.cancellation_requested = True
                    self._transition(record, JobState.CANCELLED)
                self._queue.clear()
                for job_id in self._active_jobs:
                    self._jobs[job_id].cancellation_requested = True
                processes = tuple(self._processes.values())
                self._condition.notify_all()
            else:
                processes = tuple(self._processes.values())

        for process in processes:
            _terminate_process_tree(process, self._cancel_grace_seconds)
        if wait and self._scheduler_started:
            self._scheduler.join()
            with self._condition:
                runners = tuple(self._runner_threads)
            for runner in runners:
                runner.join()

    def _schedule(self) -> None:
        while True:
            with self._condition:
                while not self._shutdown and (
                    not self._queue or len(self._active_jobs) >= self._max_active_jobs
                ):
                    self._condition.wait()
                if self._shutdown:
                    return
                job_id = self._queue.popleft()
                record = self._jobs[job_id]
                self._active_jobs.add(job_id)
                self._transition(record, JobState.PREPARING)
                runner = threading.Thread(
                    target=self._run_worker,
                    args=(job_id,),
                    name=f"ttsforge-job-{job_id}",
                    daemon=True,
                )
                self._runner_threads.add(runner)
                runner.start()

    def _run_worker(self, job_id: str) -> None:
        process: subprocess.Popen[str] | None = None
        protocol_error: ErrorView | None = None
        try:
            with self._condition:
                record = self._jobs[job_id]
                if record.cancellation_requested:
                    self._transition(record, JobState.CANCELLED)
                    return
                payload = record.payload

            process = subprocess.Popen(
                self._worker_command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=None,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                **_process_group_options(),
            )
            with self._condition:
                self._processes[job_id] = process
                should_cancel = self._jobs[job_id].cancellation_requested

            if should_cancel:
                _terminate_process_tree(process, self._cancel_grace_seconds)
            else:
                if process.stdin is None or process.stdout is None:
                    raise OSError("Worker pipes were not created.")
                process.stdin.write(payload + "\n")
                process.stdin.close()
                while line := process.stdout.readline(_MAX_PROTOCOL_LINE_BYTES + 1):
                    if len(
                        line.encode("utf-8")
                    ) > _MAX_PROTOCOL_LINE_BYTES or not line.endswith("\n"):
                        protocol_error = _protocol_error(
                            "Worker output line is invalid."
                        )
                        _terminate_process_tree(process, self._cancel_grace_seconds)
                        break
                    try:
                        message = json.loads(line, parse_constant=_reject_json_constant)
                        self._consume_message(job_id, message)
                    except (json.JSONDecodeError, _WorkerProtocolError) as error:
                        protocol_error = _protocol_error(str(error))
                        _terminate_process_tree(process, self._cancel_grace_seconds)
                        break

            self._finish_worker(job_id, process.wait(), protocol_error)
        except OSError as error:
            _LOG.error("Worker process I/O failed: %s", type(error).__name__)
            with self._condition:
                record = self._jobs[job_id]
                if record.cancellation_requested:
                    self._transition(record, JobState.CANCELLED)
                else:
                    self._fail_job(
                        record,
                        ErrorView(
                            type="WorkerProcessError",
                            message="Unable to start or communicate with the worker.",
                            category="worker",
                            code="worker_process_error",
                        ),
                    )
        except Exception as error:
            _LOG.error("Worker supervision failed: %s", type(error).__name__)
            with self._condition:
                record = self._jobs[job_id]
                if record.cancellation_requested:
                    self._transition(record, JobState.CANCELLED)
                else:
                    self._fail_job(
                        record,
                        ErrorView(
                            type="WorkerSupervisorError",
                            message="The conversion worker could not be supervised.",
                            category="worker",
                            code="worker_supervision_error",
                        ),
                    )
        finally:
            if process is not None:
                if process.stdin is not None and not process.stdin.closed:
                    try:
                        process.stdin.close()
                    except OSError:
                        pass
                if process.stdout is not None:
                    process.stdout.close()
                if process.poll() is None:
                    _terminate_process_tree(process, self._cancel_grace_seconds)
            with self._condition:
                self._processes.pop(job_id, None)
                self._active_jobs.discard(job_id)
                self._runner_threads.discard(threading.current_thread())
                self._condition.notify_all()

    def _finish_worker(
        self,
        job_id: str,
        return_code: int,
        protocol_error: ErrorView | None,
    ) -> None:
        with self._condition:
            record = self._jobs[job_id]
            if record.cancellation_requested:
                self._transition(record, JobState.CANCELLED)
            elif protocol_error is not None:
                self._fail_job(record, protocol_error)
            elif record.error is not None:
                self._transition(record, JobState.FAILED)
            elif return_code != 0:
                self._fail_job(record, _worker_exit_error(return_code))
            elif record.result is None:
                self._fail_job(
                    record,
                    _protocol_error("Worker exited without a result event."),
                )
            else:
                self._transition(record, JobState.COMPLETED)

    def _fail_job(self, record: _MutableJobRecord, error: ErrorView) -> None:
        record.error = error
        self._append_event(record, {"type": "job.error", "error": json_value(error)})
        self._transition(record, JobState.FAILED)

    def _consume_message(self, job_id: str, message: object) -> None:
        if not isinstance(message, dict) or not isinstance(message.get("type"), str):
            raise _WorkerProtocolError("Worker message must be a typed JSON object.")
        message_type = message["type"]
        with self._condition:
            record = self._jobs[job_id]
            if message_type == "job.state":
                state_value = message.get("state")
                if state_value == JobState.PREPARING.value:
                    if record.state not in {JobState.PREPARING, JobState.RUNNING}:
                        raise _WorkerProtocolError(
                            "Worker state transition is invalid."
                        )
                    if record.state is JobState.RUNNING:
                        raise _WorkerProtocolError("Worker moved back to preparing.")
                elif state_value == JobState.RUNNING.value:
                    if record.state not in {JobState.PREPARING, JobState.RUNNING}:
                        raise _WorkerProtocolError(
                            "Worker state transition is invalid."
                        )
                    self._transition(record, JobState.RUNNING)
                else:
                    raise _WorkerProtocolError("Worker state is unsupported.")
            elif message_type == "job.prepared":
                if record.state is not JobState.PREPARING:
                    raise _WorkerProtocolError(
                        "Worker prepared outside preparation state."
                    )
                record.project = _optional_path(message.get("project"))
                record.output = _optional_path(message.get("output"))
                self._append_event(record, message)
            elif message_type == "workflow.event":
                if record.state is not JobState.RUNNING:
                    raise _WorkerProtocolError(
                        "Workflow progress arrived before execution."
                    )
                event = _application_event(message.get("event"))
                record.progress = event
                self._append_event(
                    record,
                    {"type": "workflow.event", "event": json_value(event)},
                )
            elif message_type == "job.result":
                if record.state is not JobState.RUNNING or record.result is not None:
                    raise _WorkerProtocolError(
                        "Worker result event is out of sequence."
                    )
                result = _conversion_result(message.get("result"))
                record.result = result
                self._append_event(
                    record,
                    {"type": "job.result", "result": json_value(result)},
                )
            elif message_type == "job.error":
                if record.error is not None:
                    raise _WorkerProtocolError("Worker emitted multiple error events.")
                error = _error_view(message.get("error"))
                record.error = error
                self._append_event(
                    record,
                    {"type": "job.error", "error": json_value(error)},
                )
            else:
                raise _WorkerProtocolError("Worker message type is unsupported.")

    def _append_event(
        self, record: _MutableJobRecord, event: Mapping[str, object]
    ) -> None:
        encoded = json_value(event)
        if not isinstance(encoded, dict):
            raise TypeError("Job events must serialize to JSON objects.")
        record.event_sequence += 1
        record.event_history.append(
            JobEventRecord(
                sequence=record.event_sequence,
                timestamp=datetime.now(timezone.utc).isoformat(),
                event=encoded,
            )
        )

    def _transition(self, record: _MutableJobRecord, state: JobState) -> None:
        if record.state is state:
            return
        record.state = state
        now = datetime.now(timezone.utc)
        if (
            state in {JobState.PREPARING, JobState.RUNNING}
            and record.started_at is None
        ):
            record.started_at = now
        if state in _TERMINAL_STATES:
            record.finished_at = now
        self._append_event(record, {"type": "job.state", "state": state.value})

    def _require_job(self, job_id: str) -> _MutableJobRecord:
        try:
            return self._jobs[job_id]
        except KeyError:
            raise KeyError(f"Unknown job id: {job_id}") from None

    def _snapshot(self, record: _MutableJobRecord) -> JobRecord:
        return JobRecord(
            id=record.id,
            state=record.state,
            created_at=record.created_at,
            started_at=record.started_at,
            finished_at=record.finished_at,
            request=record.request,
            project=record.project,
            output=record.output,
            progress=record.progress,
            result=record.result,
            error=record.error,
            event_sequence=record.event_sequence,
            event_history=tuple(record.event_history),
        )


def _new_job_id() -> str:
    return str(uuid.uuid4())


def _process_group_options() -> dict[str, Any]:
    if os.name == "nt":
        return {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)}
    return {"start_new_session": True}


def _terminate_process_tree(
    process: subprocess.Popen[str], grace_seconds: float
) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        try:
            process.send_signal(getattr(signal, "CTRL_BREAK_EVENT", 1))
        except OSError:
            process.terminate()
    else:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=grace_seconds)
        return
    except subprocess.TimeoutExpired:
        pass
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=grace_seconds,
            )
        except (OSError, subprocess.TimeoutExpired):
            process.kill()
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    try:
        process.wait(timeout=grace_seconds)
    except subprocess.TimeoutExpired:
        process.kill()


def _reject_json_constant(value: str) -> None:
    raise _WorkerProtocolError(f"Unsupported JSON constant: {value}.")


def _protocol_error(reason: str) -> ErrorView:
    return ErrorView(
        type="WorkerProtocolError",
        message="The conversion worker returned invalid protocol data.",
        category="worker",
        code="worker_protocol_error",
        details={"reason": reason},
    )


def _worker_exit_error(return_code: int) -> ErrorView:
    return ErrorView(
        type="WorkerExitedError",
        message="The conversion worker exited before completing the job.",
        category="worker",
        code="worker_exit",
        details={"exit_code": return_code},
    )


def _application_event(value: object) -> ApplicationEvent:
    if not isinstance(value, dict):
        raise _WorkerProtocolError("Workflow event must be a JSON object.")
    stage = value.get("stage")
    kind = value.get("kind")
    if not isinstance(stage, str) or not isinstance(kind, str):
        raise _WorkerProtocolError("Workflow event stage and kind are required.")
    details = value.get("details", {})
    if not isinstance(details, dict):
        raise _WorkerProtocolError("Workflow event details must be an object.")
    return ApplicationEvent(
        stage=stage,
        kind=kind,
        message=_optional_string(value.get("message")),
        package=_optional_string(value.get("package")),
        selector=_optional_string(value.get("selector")),
        current=_optional_integer(value.get("current")),
        total=_optional_integer(value.get("total")),
        elapsed_seconds=_optional_number(value.get("elapsed_seconds")),
        details=details,
    )


def _conversion_result(value: object) -> ConversionResultView:
    if not isinstance(value, dict):
        raise _WorkerProtocolError("Worker result must be a JSON object.")
    output = value.get("output")
    workspace = value.get("workspace")
    workspace_mode = value.get("workspace_mode")
    if not isinstance(output, str) or not isinstance(workspace_mode, str):
        raise _WorkerProtocolError(
            "Worker result output and workspace mode are required."
        )
    if workspace is not None and not isinstance(workspace, str):
        raise _WorkerProtocolError("Worker result workspace must be a path or null.")
    return ConversionResultView(
        output=Path(output),
        workspace=Path(workspace) if workspace is not None else None,
        workspace_mode=workspace_mode,
        executed_stages=_string_tuple(value.get("executed_stages")),
        reused_stages=_string_tuple(value.get("reused_stages")),
        warnings=_string_tuple(value.get("warnings", [])),
        variant=_optional_string(value.get("variant")),
    )


def _error_view(value: object) -> ErrorView:
    if not isinstance(value, dict):
        raise _WorkerProtocolError("Worker error must be a JSON object.")
    error_type = value.get("type")
    message = value.get("message")
    details = value.get("details", {})
    if not isinstance(error_type, str) or not isinstance(message, str):
        raise _WorkerProtocolError("Worker error type and message are required.")
    if not isinstance(details, dict):
        raise _WorkerProtocolError("Worker error details must be an object.")
    return ErrorView(
        type=error_type,
        message=message,
        category=_optional_string(value.get("category")),
        code=_optional_string(value.get("code")),
        stage=_optional_string(value.get("stage")),
        package=_optional_string(value.get("package")),
        selector=_optional_string(value.get("selector")),
        details=details,
    )


def _optional_path(value: object) -> Path | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise _WorkerProtocolError("Worker path values must be strings or null.")
    return Path(value)


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise _WorkerProtocolError("Worker string values must be strings or null.")
    return value


def _optional_integer(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise _WorkerProtocolError("Worker integer values must be integers or null.")
    return value


def _optional_number(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _WorkerProtocolError("Worker numeric values must be numbers or null.")
    number = float(value)
    if not math.isfinite(number):
        raise _WorkerProtocolError("Worker numeric values must be finite.")
    return number


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise _WorkerProtocolError(
            "Worker result stage collections must be string lists."
        )
    return tuple(value)
