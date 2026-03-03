from __future__ import annotations

from html import escape
from pathlib import Path

from .models import Report


def write_report_html(report: Report, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    for finding in report.findings:
        rows.append(
            "<tr>"
            f"<td>{escape(finding.severity)}</td>"
            f"<td>{escape(finding.code)}</td>"
            f"<td>{escape(finding.message)}</td>"
            f"<td>{escape(finding.location or '')}</td>"
            "</tr>"
        )
    rows_html = "\n".join(rows) if rows else "<tr><td colspan='4'>No findings</td></tr>"
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>MS/CLE Report</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #ccc; padding: 8px; text-align: left; }}
    th {{ background: #f4f4f4; }}
  </style>
</head>
<body>
  <h1>Report: {escape(report.command)}</h1>
  <p>Generated at: {escape(report.generated_at.isoformat())}</p>
  <p>Summary - total: {report.summary.total}, BLOCKER: {report.summary.blocker}, WARN: {report.summary.warn}, INFO: {report.summary.info}</p>
  <table>
    <thead>
      <tr><th>Severity</th><th>Code</th><th>Message</th><th>Location</th></tr>
    </thead>
    <tbody>
      {rows_html}
    </tbody>
  </table>
</body>
</html>
"""
    path.write_text(html, encoding="utf-8")
