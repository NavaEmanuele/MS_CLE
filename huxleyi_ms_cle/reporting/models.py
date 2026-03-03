from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class Finding(BaseModel):
    code: str
    message: str
    severity: str
    location: str | None = None
    details: dict[str, Any] | None = None


class Summary(BaseModel):
    total: int
    blocker: int
    warn: int
    info: int


class Report(BaseModel):
    command: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    summary: Summary
    findings: list[Finding]
    metadata: dict[str, Any] = Field(default_factory=dict)


def build_summary(findings: list[Finding]) -> Summary:
    blocker = sum(1 for f in findings if f.severity == "BLOCKER")
    warn = sum(1 for f in findings if f.severity == "WARN")
    info = sum(1 for f in findings if f.severity == "INFO")
    return Summary(total=len(findings), blocker=blocker, warn=warn, info=info)
