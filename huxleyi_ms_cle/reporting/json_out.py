from __future__ import annotations

import json
from pathlib import Path

from .models import Report


def write_report_json(report: Report, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = report.model_dump(mode="json")
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
