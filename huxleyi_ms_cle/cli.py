from __future__ import annotations

import argparse
import json
import shutil
import tempfile
import traceback
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from .reporting import Finding, Report, build_summary, write_report_html, write_report_json

SEVERITY_BLOCKER = "BLOCKER"
SEVERITY_WARN = "WARN"
SEVERITY_INFO = "INFO"


def _estimate_profile(file_paths: list[str]) -> str:
    lower = [p.lower() for p in file_paths]
    has_cle = any("cle" in p or "cl_" in p for p in lower)
    has_ms = any("ms" in p or "ms1" in p or "stab" in p or "instab" in p for p in lower)
    if has_cle and has_ms:
        return "mscle"
    if has_cle:
        return "cle"
    return "ms"


def _copy_entry(src: Path, dst: Path) -> None:
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True)
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)


def _write_reports(outdir: Path, report: Report) -> None:
    write_report_json(report, outdir / "report.json")
    write_report_html(report, outdir / "report.html")


def _ingest(zip_path: Path, workspace: Path) -> int:
    findings: list[Finding] = []
    workspace.mkdir(parents=True, exist_ok=True)

    if not zip_path.exists():
        findings.append(
            Finding(
                code="ZIP_NOT_FOUND",
                message=f"Zip file not found: {zip_path}",
                severity=SEVERITY_BLOCKER,
                location=str(zip_path),
            )
        )
        report = Report(
            command="ingest",
            summary=build_summary(findings),
            findings=findings,
            metadata={"source_zip": str(zip_path), "workspace": str(workspace)},
        )
        _write_reports(workspace, report)
        return 2

    with tempfile.TemporaryDirectory() as tempdir:
        temp_root = Path(tempdir)
        with zipfile.ZipFile(zip_path, "r") as archive:
            archive.extractall(temp_root)

        top_level = list(temp_root.iterdir())
        if len(top_level) == 1 and top_level[0].is_dir():
            source_root = top_level[0]
        else:
            source_root = temp_root

        for entry in source_root.iterdir():
            _copy_entry(entry, workspace / entry.name)

    main_files = sorted(
        str(path.relative_to(workspace)).replace("\\", "/")
        for path in workspace.rglob("*")
        if path.is_file() and path.name not in {"manifest.json", "report.json", "report.html"}
    )[:200]

    manifest = {
        "source_zip": str(zip_path.resolve()),
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "main_files": main_files,
        "estimated_profile": _estimate_profile(main_files),
    }
    (workspace / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=True, indent=2), encoding="utf-8")

    findings.append(
        Finding(
            code="INGEST_COMPLETED",
            message=f"Ingest completed. Extracted {len(main_files)} files (top 200 listed in manifest).",
            severity=SEVERITY_INFO,
            location=str(workspace),
        )
    )
    report = Report(
        command="ingest",
        summary=build_summary(findings),
        findings=findings,
        metadata={"source_zip": str(zip_path), "workspace": str(workspace), "manifest": str(workspace / "manifest.json")},
    )
    _write_reports(workspace, report)
    return 0


def _validate(workspace: Path, outdir: Path) -> int:
    findings: list[Finding] = []

    if not workspace.exists():
        findings.append(
            Finding(
                code="WORKSPACE_NOT_FOUND",
                message=f"Workspace does not exist: {workspace}",
                severity=SEVERITY_BLOCKER,
                location=str(workspace),
            )
        )
    else:
        findings.append(
            Finding(
                code="VALIDATION_EXECUTED",
                message="Minimal validation completed.",
                severity=SEVERITY_INFO,
                location=str(workspace),
            )
        )

    report = Report(
        command="validate",
        summary=build_summary(findings),
        findings=findings,
        metadata={"workspace": str(workspace), "outdir": str(outdir)},
    )
    _write_reports(outdir, report)
    return 2 if any(f.severity == SEVERITY_BLOCKER for f in findings) else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="huxleyi_ms_cle")
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest_parser = subparsers.add_parser("ingest", help="Extract a zip package into a workspace")
    ingest_parser.add_argument("--zip", dest="zip_path", required=True, help="Path to input zip")
    ingest_parser.add_argument("--workspace", required=True, help="Workspace directory")

    validate_parser = subparsers.add_parser("validate", help="Run minimal validation on a workspace")
    validate_parser.add_argument("workspace", help="Workspace directory")
    validate_parser.add_argument("--out", required=True, help="Output directory for reports")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "ingest":
            return _ingest(Path(args.zip_path), Path(args.workspace))
        if args.command == "validate":
            return _validate(Path(args.workspace), Path(args.out))
    except Exception:
        traceback.print_exc()
        return 1
    return 1
