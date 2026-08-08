"""Work and platform status enumerations."""

from enum import StrEnum

from pydantic import BaseModel, Field


class WorkStatus(StrEnum):
    ACCEPTED = "ACCEPTED"
    PROCESSING = "PROCESSING"
    RETRY_WAIT = "RETRY_WAIT"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class WorkerStatus(StrEnum):
    RUNNING = "RUNNING"
    RESTARTING = "RESTARTING"
    OUT_OF_SERVICE = "OUT_OF_SERVICE"
    SLOW = "SLOW"


class FailureMode(StrEnum):
    NORMAL = "normal"
    CRASH = "crash"
    SLOW = "slow"
    KILLED = "killed"
    FAIL_ON_CLAIM = "fail_on_claim"


class WorkSubmitRequest(BaseModel):
    id: str = Field(min_length=1, description="Client idempotency key")
    type: str = Field(min_length=1)
    body: dict = Field(default_factory=dict)


class WorkResponse(BaseModel):
    id: str
    type: str
    body: dict
    status: WorkStatus
    attempt_count: int
    max_attempts: int
    created_at: str
    updated_at: str
    accepted_at: str
    next_retry_at: str | None = None
    assigned_worker_id: str | None = None
    lease_expires_at: str | None = None
    last_error: str | None = None
    completed_at: str | None = None


class WorkerRegisterRequest(BaseModel):
    id: str = Field(min_length=1)


class WorkerResponse(BaseModel):
    id: str
    status: WorkerStatus
    restart_count: int
    max_restarts: int
    last_heartbeat_at: str | None = None
    failure_mode: FailureMode
    release_version: str
    created_at: str
    updated_at: str


class WorkCompleteRequest(BaseModel):
    worker_id: str = Field(min_length=1)
    result: dict = Field(default_factory=dict)


class WorkFailRequest(BaseModel):
    worker_id: str = Field(min_length=1)
    error: str = Field(default="Worker reported processing failure")


class FailureModeRequest(BaseModel):
    mode: FailureMode


class WorkOverviewItem(BaseModel):
    id: str
    type: str
    status: WorkStatus
    priority: str
    attempt_count: int
    max_attempts: int
    assigned_worker_id: str | None = None
    created_at: str
    lease_expires_at: str | None = None
    next_retry_at: str | None = None
    failure_reason: str | None = None


class WorkerOverviewItem(BaseModel):
    id: str
    status: WorkerStatus
    current_work_id: str | None = None
    last_heartbeat_at: str | None = None
    last_activity_at: str | None = None
    lease_expires_at: str | None = None
    failure_mode: str
    restart_count: int
    max_restarts: int


class OperatorSummary(BaseModel):
    total_work: int
    accepted: int
    processing: int
    retry_wait: int
    completed: int
    failed: int
    registered_workers: int
    health: str
    health_detail: str


class EventRecord(BaseModel):
    id: int
    timestamp: str
    event_type: str
    action: str
    work_id: str | None = None
    worker_id: str | None = None
    subject_type: str
    subject_id: str
    reason: str
    details: dict | None = None


class OperatorSnapshot(BaseModel):
    summary: OperatorSummary
    work: list[WorkOverviewItem]
    workers: list[WorkerOverviewItem]
    events: list[EventRecord] = Field(default_factory=list)
