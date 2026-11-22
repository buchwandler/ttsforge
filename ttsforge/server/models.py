"""HTTP request models kept separate from application dataclasses."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SourceInspectRequest(StrictModel):
    path: str


class AudiobookRequestModel(StrictModel):
    source: str
    project: str | None = None
    chapters: str | None = None
    output: str | None = None
    language: str | None = None
    engine: str | None = None
    target: str | None = None
    voice: str | None = None
    engine_options: dict[str, JsonValue] = Field(default_factory=dict)
    speed: float | None = None
    spacy: Literal["off", "auto", "sm", "md", "lg", "trf"] | None = None
    speech_profile: str | None = None
    pause_timing: Literal["fixed", "natural", "engaging"] | None = None
    bitrate: str | int | None = None
    target_lufs: float | None = None
    title: str | None = None
    author: str | None = None
    cover: str | None = None
    offline: bool = False
    refresh: bool = False
    rebuild_from: str | None = None
    replace_output: bool = False
    fresh: bool = False
    new_variant: bool = False


class JobSubmissionModel(StrictModel):
    request: AudiobookRequestModel
    explicit_fields: list[str] = Field(default_factory=list)


class SpacyEnsureRequest(StrictModel):
    language: str
    tier: Literal["sm", "md", "lg", "trf"]
    offline: bool = False


class SpeechProfileInspectRequest(StrictModel):
    path: str


class ApiErrorModel(StrictModel):
    type: str
    message: str
    category: str | None
    code: str | None
    stage: str | None
    package: str | None
    selector: str | None
    details: dict[str, JsonValue] = Field(default_factory=dict)


class ApiErrorResponseModel(StrictModel):
    error: ApiErrorModel


class HealthResponseModel(StrictModel):
    ok: bool


class SystemResponseModel(StrictModel):
    api_version: int
    ttsforge_version: str | None
    python_version: str
    capabilities: dict[str, bool]


class PythonRuntimeResponseModel(StrictModel):
    version: str
    executable: str


class PackageRuntimeResponseModel(StrictModel):
    ttsforge: str | None
    readio: str | None


class RuntimeToolResponseModel(StrictModel):
    available: bool
    path: str | None


class AudioExportRuntimeResponseModel(StrictModel):
    available: bool
    version: str | None


class AudioRuntimeResponseModel(StrictModel):
    audioexport: AudioExportRuntimeResponseModel
    ffmpeg: RuntimeToolResponseModel
    ffprobe: RuntimeToolResponseModel


class RuntimeProblemResponseModel(StrictModel):
    code: Literal[
        "ffmpeg_missing",
        "ffprobe_missing",
        "audioexport_missing",
        "readio_missing",
    ]
    message: str


class RuntimeStatusResponseModel(StrictModel):
    python: PythonRuntimeResponseModel
    packages: PackageRuntimeResponseModel
    audio: AudioRuntimeResponseModel
    ready: bool
    problems: list[RuntimeProblemResponseModel]


class BookChapterResponseModel(StrictModel):
    number: int
    title: str
    source_id: str | None
    char_count: int | None


class BookInspectionResponseModel(StrictModel):
    source: str
    kind: str
    title: str | None
    author: str | None
    language: str | None
    chapters: list[BookChapterResponseModel]
    cover: str | None


class SourceImportStatusResponseModel(StrictModel):
    source_id: str
    path: str
    managed: bool
    temporary: bool
    retention_days: int
    claimed: bool
    created_at: str
    last_used_at: str | None


class SourceImportResponseModel(SourceImportStatusResponseModel):
    inspection: BookInspectionResponseModel


class DeleteSourceImportResponseModel(StrictModel):
    source_id: str
    deleted: bool


class EngineChoiceResponseModel(StrictModel):
    id: str
    version: str | None
    installed: bool
    runnable: bool
    features: list[str]
    reason: str | None


class TargetChoiceResponseModel(StrictModel):
    id: str
    languages: list[str]
    status: str
    runtime_available: bool
    default_voice: str | None
    voice_count: int
    qualities: list[str]
    voice_mode: str | None
    sample_rate: int | None
    features: list[str]
    reference_only: bool


class VoiceChoiceResponseModel(StrictModel):
    id: str
    language: str | None
    locale: str | None
    language_label: str | None
    gender: str
    default: bool
    runtime_available: bool


class EngineOptionResponseModel(StrictModel):
    name: str
    value_type: str | None
    required: bool
    default: JsonValue
    choices: list[JsonValue]
    minimum: int | float | None
    maximum: int | float | None
    description: str
    identity_affecting: bool
    runtime_only: bool


class SpacyModelResponseModel(StrictModel):
    language: str
    tier: str
    model: str
    installed: bool
    spacy_version: str | None
    model_version: str | None


class SpeechProfileChoiceResponseModel(StrictModel):
    path: str
    name: str


class SpeechProfilesResponseModel(StrictModel):
    directory: str
    profiles: list[SpeechProfileChoiceResponseModel]


class SpeechProfileInspectResponseModel(StrictModel):
    path: str
    valid: bool


class SetupOriginsResponseModel(StrictModel):
    explicit: list[str]
    project: list[str]
    derived: list[str]


class SetupResolutionResponseModel(StrictModel):
    project: str
    configuration_variant: str | None
    reused_setup: bool
    inspection: BookInspectionResponseModel
    request: AudiobookRequestModel
    origins: SetupOriginsResponseModel


class WorkflowStepResponseModel(StrictModel):
    stage: str
    package: str
    action: str
    selector: str | None
    reason: str
    state: str


class WorkflowPlanResponseModel(StrictModel):
    source: str
    workspace: str | None
    workspace_mode: str
    output: str | None
    steps: list[WorkflowStepResponseModel]
    warnings: list[str]
    variant: str | None


class PreflightResponseModel(StrictModel):
    project: str
    configuration_variant: str | None
    reused_setup: bool
    spacy_model: SpacyModelResponseModel | None
    request: AudiobookRequestModel
    workflow: WorkflowPlanResponseModel


class ProjectSetupResponseModel(StrictModel):
    project: str
    variant: str | None
    saved_setup: AudiobookRequestModel | None


class ProjectVariantResponseModel(StrictModel):
    variant_key: str
    output: str | None
    engine: str | None
    target: str | None
    voice: str | None
    error: str | None


class ProjectInfoResponseModel(StrictModel):
    project: str
    saved_setup: AudiobookRequestModel | None
    workflow: WorkflowPlanResponseModel | None
    variants: list[ProjectVariantResponseModel]


class ApplicationEventResponseModel(StrictModel):
    stage: str
    kind: str
    message: str | None
    package: str | None
    selector: str | None
    current: int | None
    total: int | None
    elapsed_seconds: float | None
    details: dict[str, JsonValue]


class ConversionResultResponseModel(StrictModel):
    output: str
    workspace: str | None
    workspace_mode: str
    executed_stages: list[str]
    reused_stages: list[str]
    warnings: list[str]
    variant: str | None


JobStateLiteral = Literal[
    "queued", "preparing", "running", "completed", "failed", "cancelled"
]


class JobStateEventResponseModel(StrictModel):
    type: Literal["job.state"]
    state: JobStateLiteral


class JobPreparedEventResponseModel(StrictModel):
    type: Literal["job.prepared"]
    project: str
    output: str


class JobWorkflowEventResponseModel(StrictModel):
    type: Literal["workflow.event"]
    event: ApplicationEventResponseModel


JobEventPayload = Annotated[
    JobStateEventResponseModel
    | JobPreparedEventResponseModel
    | JobWorkflowEventResponseModel,
    Field(discriminator="type"),
]


class JobCreateResponseModel(StrictModel):
    id: str
    state: JobStateLiteral


class JobSummaryResponseModel(StrictModel):
    id: str
    state: JobStateLiteral
    created_at: str
    started_at: str | None
    finished_at: str | None
    project: str | None
    output: str | None
    event_sequence: int


class JobListResponseModel(StrictModel):
    jobs: list[JobSummaryResponseModel]


class JobStatusResponseModel(JobSummaryResponseModel):
    progress: ApplicationEventResponseModel | None
    result: ConversionResultResponseModel | None
    error: ApiErrorModel | None


class JobEventResponseModel(StrictModel):
    seq: int
    timestamp: str
    event: JobEventPayload


class JobEventsPageResponseModel(StrictModel):
    first: int
    next: int
    truncated: bool
    events: list[JobEventResponseModel]
