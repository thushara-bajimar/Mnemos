"""Pydantic request schemas (validation for every write endpoint)."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

SourceType = Literal["user", "agent", "document", "tool", "web", "system", "unknown"]
MemoryType = Literal["episodic", "semantic", "procedural", "preference", "working", "relational"]


class MemoryIn(BaseModel):
    content: str = Field(..., min_length=1, max_length=8000)
    source_type: SourceType = "user"
    source_id: str | None = Field(None, max_length=200)
    source_label: str | None = Field(None, max_length=200)
    agent_id: str | None = Field(None, max_length=64)
    session_id: str | None = Field(None, max_length=64)
    task_id: str | None = Field(None, max_length=64)
    tags: list[str] = Field(default_factory=list, max_length=20)
    confidence: float | None = Field(None, ge=0, le=1)
    ttl_hours: float | None = Field(None, gt=0, le=24 * 365)
    memory_type: MemoryType | None = None
    importance: float | None = Field(None, ge=0, le=1)
    derived_from: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("content")
    @classmethod
    def strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("content must not be blank")
        return v


class BatchIn(BaseModel):
    items: list[MemoryIn] = Field(..., min_length=1, max_length=200)


class EditIn(BaseModel):
    content: str = Field(..., min_length=1, max_length=8000)
    reason: str = Field("manual edit", max_length=300)
    actor: str = Field("user", max_length=64)


class ConfirmIn(BaseModel):
    approve: bool
    actor: str = "user"


class SearchIn(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    mode: Literal["hybrid", "keyword", "semantic", "structured", "graph"] = "hybrid"
    limit: int = Field(10, ge=1, le=100)
    memory_types: list[MemoryType] | None = None
    agent_id: str | None = None
    task_id: str | None = None
    source_types: list[SourceType] | None = None
    min_confidence: float = Field(0.0, ge=0, le=1)
    include_inactive: bool = False


class AskIn(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    task_id: str | None = None


class ContextIn(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    budget: int = Field(1000, ge=50, le=20000)
    task_id: str | None = None
    mode: Literal["hybrid", "keyword", "semantic", "structured", "graph"] = "hybrid"
    memory_types: list[MemoryType] | None = None
    compact: bool = True


class CompareIn(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    budgets: list[int] = Field(default_factory=lambda: [500, 1000, 2000, 5000], max_length=8)


class ResolveIn(BaseModel):
    resolution: Literal["keep_a", "keep_b", "keep_both"]
    actor: str = "user"


class ForgetPlanIn(BaseModel):
    scope: Literal["id", "topic", "entity", "source"]
    value: str = Field(..., min_length=1, max_length=500)
    include_derived: bool = True


class ForgetExecIn(BaseModel):
    confirm_token: str = Field(..., min_length=8, max_length=64)
    requested_by: str = Field("user", max_length=64)


class ChatIn(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    task_id: str | None = None


class TaskIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    goal: str = Field(..., min_length=1, max_length=1000)
    steps: list[str] | None = Field(None, max_length=20)
    constraints: list[str] | None = Field(None, max_length=20)


class WorkIn(BaseModel):
    max_steps: int = Field(2, ge=1, le=20)


class HandoverIn(BaseModel):
    task_id: str
    from_agent: str = "atlas"
    to_agent: str = "bolt"
    token_budget: int = Field(1000, ge=200, le=20000)
    notes: str = Field("", max_length=500)


class ToolIn(BaseModel):
    agent_id: str = Field(..., min_length=2, max_length=32)
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)


class RegisterAgentIn(BaseModel):
    agent_id: str
    name: str
    integration: str = "REST"


class EvalIn(BaseModel):
    suite: Literal["scenarios", "storage", "context", "all"] = "all"


class SettingsIn(BaseModel):
    values: dict[str, Any]


class ResetIn(BaseModel):
    confirm: Literal["RESET"]
