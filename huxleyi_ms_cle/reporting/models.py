from __future__ import annotations

from dataclasses import dataclass, asdict
from enum import Enum
from typing import Any


class Severity(str, Enum):
    BLOCKER = "BLOCKER"
    WARN = "WARN"
    INFO = "INFO"


@dataclass(slots=True)
class Finding:
    code: str
    severity: Severity
    message: str
    target: str | None = None
    suggestion: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["severity"] = self.severity.value
        return data
