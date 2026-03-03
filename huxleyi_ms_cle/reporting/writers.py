from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from .models import Finding, Severity


def _summary(findings: list[Finding]) -> dict[str, int]:
    counts = Counter(f.severity.value for f in findings)
    return {
        Severity.BLOCKER.value: counts.get(Severity.BLOCKER.value, 0),
        Severity.WARN.value: counts.get(Severity.WARN.value, 0),
        Severity.INFO.value: counts.get(Severity.INFO.value, 0),
        "TOTAL": len(findings),
    }


def write_json_report(findings: list[Finding], out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "summary": _summary(findings),
        "findings": [f.to_dict() for f in findings],
    }
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return out_path


def write_html_report(findings: list[Finding], out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    summary = _summary(findings)
    rows = "\n".join(
        f"<tr><td>{f.severity.value}</td><td>{f.code}</td><td>{f.target or ''}</td><td>{f.message}</td><td>{f.suggestion or ''}</td></tr>"
        for f in findings
    )
    html = f"""<!doctype html>
<html lang=\"it\">
<head>
  <meta charset=\"utf-8\" />
  <title>MS-CLE Validation Report</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
    th {{ background: #f5f5f5; }}
    .BLOCKER {{ color: #b00020; font-weight: bold; }}
    .WARN {{ color: #af6f00; font-weight: bold; }}
    .INFO {{ color: #005a9c; }}
  </style>
</head>
<body>
  <h1>MS-CLE Validation Report</h1>
  <p>BLOCKER: {summary['BLOCKER']} | WARN: {summary['WARN']} | INFO: {summary['INFO']} | TOTAL: {summary['TOTAL']}</p>
  <table>
    <thead>
      <tr><th>Severity</th><th>Code</th><th>Target</th><th>Message</th><th>Suggestion</th></tr>
    </thead>
    <tbody>
      {rows}
    </tbody>
  </table>
</body>
</html>
"""
    out_path.write_text(html, encoding="utf-8")
    return out_path
