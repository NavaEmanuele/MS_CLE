from __future__ import annotations

import argparse
import sys
from pathlib import Path

from huxleyi_ms_cle.common import discover_vector_files, ensure_dir, extract_zip
from huxleyi_ms_cle.reports import SEVERITY_BLOCKER, SEVERITY_INFO, UnifiedReport
from huxleyi_ms_cle.validators.ms_validations import validate_workspace


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m huxleyi_ms_cle")
    sub = parser.add_subparsers(dest="command", required=True)

    ingest = sub.add_parser("ingest", help="Extract a ZIP package into a workspace")
    ingest.add_argument("--zip", dest="zip_path", required=True, type=Path)
    ingest.add_argument("--workspace", required=True, type=Path)

    validate = sub.add_parser("validate", help="Validate workspace data and produce report")
    validate.add_argument("workspace", type=Path)
    validate.add_argument("--out", required=True, type=Path)

    build = sub.add_parser("build", help="Run validation and build outputs")
    build.add_argument("workspace", type=Path)
    build.add_argument("--out", required=True, type=Path)

    return parser


def run_ingest(zip_path: Path, workspace: Path) -> int:
    report_out = ensure_dir(workspace / "output")
    report = UnifiedReport(command="ingest", workspace=str(workspace), outdir=str(report_out))

    if not zip_path.exists():
        report.add(SEVERITY_BLOCKER, "ZIP_NOT_FOUND", "Input ZIP does not exist.", file=str(zip_path))
        report.write(report_out)
        return 2

    extracted = extract_zip(zip_path, workspace)
    report.add(SEVERITY_INFO, "INGEST_OK", f"Extracted {len(extracted)} file(s) from archive.")
    vector_count = len(discover_vector_files(workspace))
    report.add(SEVERITY_INFO, "VECTOR_COUNT", f"Workspace contains {vector_count} vector dataset(s) after ingest.")
    report.write(report_out)
    return 0


def run_validate(workspace: Path, outdir: Path, command: str = "validate") -> int:
    report = UnifiedReport(command=command, workspace=str(workspace), outdir=str(outdir))

    if not workspace.exists():
        report.add(SEVERITY_BLOCKER, "WORKSPACE_NOT_FOUND", "Workspace path does not exist.", file=str(workspace))
        report.write(outdir)
        return 2

    validate_workspace(workspace, report)
    report.write(outdir)
    return 2 if report.has_blocker else 0


def run_build(workspace: Path, outdir: Path) -> int:
    ensure_dir(outdir)
    return run_validate(workspace, outdir, command="build")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "ingest":
            return run_ingest(args.zip_path, args.workspace)
        if args.command == "validate":
            return run_validate(args.workspace, args.out)
        if args.command == "build":
            return run_build(args.workspace, args.out)
        parser.print_help()
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"Runtime error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
