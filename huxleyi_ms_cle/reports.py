from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from html import escape
from pathlib import Path

SEVERITY_BLOCKER = "BLOCKER"
SEVERITY_WARN = "WARN"
SEVERITY_INFO = "INFO"


@dataclass
class Finding:
    severity: str
    code: str
    message: str
    file: str | None = None


@dataclass
class UnifiedReport:
    command: str
    workspace: str
    outdir: str
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    findings: list[Finding] = field(default_factory=list)

    def add(self, severity: str, code: str, message: str, file: str | None = None) -> None:
        self.findings.append(Finding(severity=severity, code=code, message=message, file=file))

    @property
    def has_blocker(self) -> bool:
        return any(item.severity == SEVERITY_BLOCKER for item in self.findings)

    def to_dict(self) -> dict:
        return {
            "command": self.command,
            "workspace": self.workspace,
            "outdir": self.outdir,
            "started_at": self.started_at,
            "summary": {
                "blocker": sum(1 for f in self.findings if f.severity == SEVERITY_BLOCKER),
                "warn": sum(1 for f in self.findings if f.severity == SEVERITY_WARN),
                "info": sum(1 for f in self.findings if f.severity == SEVERITY_INFO),
            },
            "findings": [asdict(item) for item in self.findings],
        }

    def write(self, outdir: Path) -> tuple[Path, Path]:
        outdir.mkdir(parents=True, exist_ok=True)
        json_path = outdir / "report.json"
        html_path = outdir / "report.html"

        json_path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        html_path.write_text(self.to_html(), encoding="utf-8")
        return json_path, html_path

    def to_html(self) -> str:
        rows = "\n".join(
            (
                "<tr>"
                f"<td>{escape(item.severity)}</td>"
                f"<td>{escape(item.code)}</td>"
                f"<td>{escape(item.file or '-')}</td>"
                f"<td>{escape(item.message)}</td>"
                "</tr>"
            )
            for item in self.findings
        )

        return f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <title>MS/CLE Report</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 2rem; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
    th {{ background: #f5f5f5; }}
  </style>
</head>
<body>
  <h1>MS/CLE Unified Report</h1>
  <p><strong>Command:</strong> {escape(self.command)}</p>
  <p><strong>Workspace:</strong> {escape(self.workspace)}</p>
  <p><strong>Output:</strong> {escape(self.outdir)}</p>
  <table>
    <thead>
      <tr><th>Severity</th><th>Code</th><th>File</th><th>Message</th></tr>
    </thead>
    <tbody>
      {rows}
    </tbody>
  </table>
</body>
</html>
"""
