from datetime import date, datetime, time
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


def to_camel(string: str) -> str:
    parts = string.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:])


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, from_attributes=True)


# ---- enums ----


class CapabilityEnum(str, Enum):
    tasks = "tasks"
    calendar = "calendar"
    docs = "docs"
    email = "email"
    notify = "notify"


class ConnectionTypeEnum(str, Enum):
    jira = "jira"
    clickup = "clickup"
    google = "google"
    gmail = "gmail"
    line = "line"
    other = "other"


class WorkProductTypeEnum(str, Enum):
    meeting_record = "meeting_record"
    memo = "memo"
    project_plan = "project_plan"
    requirements = "requirements"
    traceability = "traceability"
    test_case = "test_case"
    change_request = "change_request"


class TaskStatusEnum(str, Enum):
    todo = "todo"
    in_progress = "in_progress"
    blocked = "blocked"
    done = "done"
    cancelled = "cancelled"


class TaskPriorityEnum(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    urgent = "urgent"


class MilestoneStatusEnum(str, Enum):
    open = "open"
    at_risk = "at_risk"
    done = "done"


class DocStatusEnum(str, Enum):
    draft = "draft"
    issued = "issued"


# ---- common ----


class ErrorResponse(CamelModel):
    code: str
    message: str
    details: dict[str, Any] | None = None


# ---- projects ----


class ProjectCreate(CamelModel):
    key: str = Field(max_length=10)
    name: str


class ProjectOut(CamelModel):
    id: UUID
    key: str
    name: str
    is_archived: bool
    created_at: datetime


class DashboardSummary(CamelModel):
    task_counts: dict[str, int]
    next_milestone: "MilestoneOut | None" = None
    due_soon: list["TaskOut"] = []
    next_event: "CalendarEventOut | None" = None


# ---- members ----


class MemberInput(CamelModel):
    name: str
    email: EmailStr | None = None
    role: str | None = None


class MemberOut(CamelModel):
    id: UUID
    name: str
    email: str | None = None
    role: str | None = None


# ---- connections / bindings ----


class ConnectionOut(CamelModel):
    id: UUID
    type: ConnectionTypeEnum
    display_name: str
    status: str
    expires_at: datetime | None = None


class BindingOut(CamelModel):
    id: UUID
    capability: CapabilityEnum
    connection_id: UUID
    config: dict[str, Any] = {}


class BindingInput(CamelModel):
    connection_id: UUID
    config: dict[str, Any] = {}


# ---- templates / numbering ----


class TemplateOut(CamelModel):
    id: UUID
    wp_type: WorkProductTypeEnum
    version: int
    uploaded_at: datetime


class NumberingRuleOut(CamelModel):
    wp_type: WorkProductTypeEnum
    prefix: str
    pattern: str
    current_seq: int
    reset_period: str


class NumberingRuleInput(CamelModel):
    prefix: str | None = None
    pattern: str | None = None
    reset_period: str | None = None


# ---- documents ----


class DocumentOut(CamelModel):
    id: UUID
    wp_type: WorkProductTypeEnum
    doc_number: str | None = None
    title: str
    status: DocStatusEnum
    created_at: datetime


class DocumentListResponse(CamelModel):
    items: list[DocumentOut]
    next_cursor: str | None = None


# ---- tasks / milestones ----


class ExternalRef(CamelModel):
    provider: str | None = None
    key: str | None = None
    url: str | None = None


class TaskOut(CamelModel):
    id: UUID
    title: str
    assignee_id: UUID | None = None
    due_date: date | None = None
    priority: TaskPriorityEnum
    status: TaskStatusEnum
    milestone_id: UUID | None = None
    external_ref: ExternalRef | dict[str, Any] = {}


class TaskInput(CamelModel):
    title: str
    description: str | None = None
    assignee_id: UUID | None = None
    due_date: date | None = None
    priority: TaskPriorityEnum = TaskPriorityEnum.medium
    milestone_id: UUID | None = None


class MilestoneOut(CamelModel):
    id: UUID
    name: str
    target_date: date | None = None
    status: MilestoneStatusEnum
    linked_task_count: int = 0


class MilestoneInput(CamelModel):
    name: str
    description: str | None = None
    target_date: date | None = None


# ---- meetings ----


class ActionItemOut(CamelModel):
    description: str
    owner_id: UUID | None = None
    due_date: date | None = None
    is_inferred: bool = False


class MeetingOut(CamelModel):
    id: UUID
    title: str
    meeting_date: date | None = None
    decisions: list[str] = []
    action_items: list[ActionItemOut] = []


# ---- calendar ----


class CalendarEventOut(CamelModel):
    id: UUID
    title: str
    starts_at: datetime
    ends_at: datetime | None = None
    recurrence_rule: str | None = None
    meet_link: str | None = None


class CalendarEventInput(CamelModel):
    title: str
    starts_at: datetime
    ends_at: datetime | None = None
    recurrence_rule: str | None = None
    attendee_member_ids: list[UUID] = []
    create_meet_link: bool = True


# ---- traceability ----


class TraceabilityCoverage(CamelModel):
    requirement_id: UUID
    code: str
    title: str
    coverage: str
    task_keys: list[str] = []
    test_case_codes: list[str] = []


class TraceabilityLinkInput(CamelModel):
    requirement_id: UUID
    task_id: UUID | None = None
    test_case_id: UUID | None = None


# ---- confirmations ----


class ExecutionAction(CamelModel):
    tool: str
    ok: bool
    ref: str | None = None
    error: str | None = None


class ExecutionResult(CamelModel):
    status: str
    actions: list[ExecutionAction] = []


# ---- notifications ----


class NotificationPreferences(CamelModel):
    enabled_types: list[str] = ["due_soon", "overdue", "meeting_soon"]
    quiet_hours_start: str | None = None
    quiet_hours_end: str | None = None
