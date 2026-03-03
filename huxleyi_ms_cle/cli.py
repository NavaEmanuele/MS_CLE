from __future__ import annotations

import argparse
import json
import shutil
import traceback
import uuid
import zipfile
from datetime import datetime, timezone
from fnmatch import fnmatch
from pathlib import Path

import yaml

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


def _load_yaml(path: Path) -> dict:
    content = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(content, dict):
        raise ValueError(f"Invalid YAML schema format: {path}")
    return content


def _load_catalog() -> dict:
    catalog_path = Path(__file__).resolve().parents[1] / "schemas" / "catalog.yaml"
    if catalog_path.exists():
        return _load_yaml(catalog_path)
    return {
        "kinds": {
            "delivery": {"fs_schema": "fs_structure.yaml"},
            "incoming": {"fs_schema": "fs_structure.yaml"},
        }
    }


def _load_fs_schema(kind: str) -> dict:
    schemas_root = Path(__file__).resolve().parents[1] / "schemas"
    catalog = _load_catalog()
    kinds = catalog.get("kinds", {})
    kind_cfg = kinds.get(kind, {})
    rel = kind_cfg.get("fs_schema")
    candidates: list[Path] = []
    if isinstance(rel, str):
        candidates.append(schemas_root / rel)
    candidates.append(schemas_root / kind / "fs_structure.yaml")
    candidates.append(schemas_root / "fs_structure.yaml")
    for candidate in candidates:
        if candidate.exists():
            return _load_yaml(candidate)
    raise FileNotFoundError(f"No fs structure schema found for kind '{kind}'")


def _load_mappings_schema() -> dict:
    schemas_root = Path(__file__).resolve().parents[1] / "schemas"
    catalog = _load_catalog()
    rel = catalog.get("kinds", {}).get("incoming", {}).get("mappings")
    candidates: list[Path] = []
    if isinstance(rel, str):
        candidates.append(schemas_root / rel)
    candidates.append(schemas_root / "incoming" / "mappings.yaml")
    for candidate in candidates:
        if candidate.exists():
            return _load_yaml(candidate)
    return {"mappings": []}


def _detect_profile_from_workspace(workspace: Path) -> str:
    top_dirs = {item.name.lower() for item in workspace.iterdir() if item.is_dir()}
    has_cle = "cle" in top_dirs or any(workspace.glob("CLE/**/*.mdb"))
    has_ms = any(name in top_dirs for name in {"ms1", "ms2", "geotec", "indagini"}) or any(workspace.glob("MS1/**/*.shp"))
    if has_cle and has_ms:
        return "mscle"
    if has_cle:
        return "cle"
    return "ms"


def _resolve_profile(workspace: Path, profiles: dict) -> str:
    manifest_path = workspace / "manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            profile = manifest.get("estimated_profile")
            if isinstance(profile, str) and profile in profiles:
                return profile
        except json.JSONDecodeError:
            pass
    detected = _detect_profile_from_workspace(workspace)
    return detected if detected in profiles else "ms"


def _is_delivery_like(workspace: Path) -> bool:
    required = {"BasiDati", "Plot"}
    optional = {"CLE", "MS1", "MS2", "GeoTec", "Indagini"}
    top = {item.name for item in workspace.iterdir() if item.is_dir()}
    return required.issubset(top) and bool(top.intersection(optional))


def _resolve_kind(workspace: Path, kind: str | None) -> str:
    if kind:
        return kind
    if workspace.exists() and workspace.is_dir() and _is_delivery_like(workspace):
        return "delivery"
    return "incoming"


def _validate_fs(workspace: Path, schema: dict, profile: str) -> list[Finding]:
    findings: list[Finding] = []
    profile_cfg = schema["profiles"][profile]
    required_dirs = profile_cfg.get("required_dirs", [])
    required_files_glob = profile_cfg.get("required_files_glob", [])

    for required_dir in required_dirs:
        required_path = workspace / required_dir
        if not required_path.exists() or not required_path.is_dir():
            findings.append(
                Finding(
                    code="FS001",
                    message=f"Required directory missing: {required_dir}",
                    severity=SEVERITY_BLOCKER,
                    location=str(required_path),
                    details={"required_dir": required_dir, "profile": profile},
                )
            )

    for pattern in required_files_glob:
        matches = [p for p in workspace.glob(pattern) if p.is_file()]
        if not matches:
            findings.append(
                Finding(
                    code="FS002",
                    message=f"Required file pattern not found: {pattern}",
                    severity=SEVERITY_BLOCKER,
                    location=str(workspace),
                    details={"pattern": pattern, "profile": profile},
                )
            )

    warn_on_extra_dirs = bool(schema.get("warn_on_extra_dirs", False))
    ignore_patterns = schema.get("ignore_dirs_glob", [])
    if warn_on_extra_dirs:
        required_top = {str(d).split("/")[0] for d in required_dirs}
        actual_top = [entry for entry in workspace.iterdir() if entry.is_dir()]
        for entry in actual_top:
            name = entry.name
            if name in required_top:
                continue
            if any(fnmatch(name, ignore) or fnmatch(str(entry.relative_to(workspace)).replace("\\", "/"), ignore) for ignore in ignore_patterns):
                continue
            findings.append(
                Finding(
                    code="FS100",
                    message=f"Extra directory found: {name}",
                    severity=SEVERITY_WARN,
                    location=str(entry),
                    details={"directory": name, "profile": profile},
                )
            )

    return findings


def _copy_path_to_dest(src: Path, dest: Path) -> str:
    if src.is_dir():
        shutil.copytree(src, dest, dirs_exist_ok=True)
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
    return str(dest)


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

    temp_parent = workspace.parent
    temp_parent.mkdir(parents=True, exist_ok=True)
    temp_root = temp_parent / f".ingest_tmp_{uuid.uuid4().hex[:10]}"
    temp_root.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(zip_path, "r") as archive:
            archive.extractall(temp_root)

        top_level = list(temp_root.iterdir())
        if len(top_level) == 1 and top_level[0].is_dir():
            source_root = top_level[0]
        else:
            source_root = temp_root

        for entry in source_root.iterdir():
            _copy_entry(entry, workspace / entry.name)
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)

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


def _normalize(source_path: Path, out_workspace: Path, kind: str | None, profile: str | None) -> int:
    source_path = source_path.resolve()
    out_workspace.mkdir(parents=True, exist_ok=True)

    resolved_kind = kind or "incoming"
    delivery_schema = _load_fs_schema("delivery")
    resolved_profile = profile or _detect_profile_from_workspace(source_path)
    if resolved_profile not in delivery_schema.get("profiles", {}):
        resolved_profile = "ms"

    required_dirs = delivery_schema["profiles"][resolved_profile].get("required_dirs", [])
    created_dirs: list[str] = []
    for dirname in required_dirs:
        target = out_workspace / dirname
        target.mkdir(parents=True, exist_ok=True)
        created_dirs.append(dirname)

    mappings_schema = _load_mappings_schema()
    mapped_items: list[dict] = []
    mappings = mappings_schema.get("mappings", [])
    if isinstance(mappings, list):
        for mapping in mappings:
            if not isinstance(mapping, dict):
                continue
            source_glob = mapping.get("source_glob")
            dest_rel = mapping.get("dest")
            if not isinstance(source_glob, str) or not isinstance(dest_rel, str):
                continue
            for matched in source_path.glob(source_glob):
                if matched.is_dir():
                    continue
                target = out_workspace / dest_rel / matched.name
                copied_to = _copy_path_to_dest(matched, target)
                mapped_items.append(
                    {
                        "source": str(matched),
                        "dest": copied_to,
                        "source_glob": source_glob,
                        "kind": resolved_kind,
                    }
                )

    workspace_manifest = {
        "source_path": str(source_path),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "kind": resolved_kind,
        "profile": resolved_profile,
        "created_dirs": created_dirs,
        "mapped_items": mapped_items,
    }
    (out_workspace / "workspace_manifest.json").write_text(
        json.dumps(workspace_manifest, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )
    return 0


def _validate(workspace: Path, outdir: Path, kind: str | None, profile: str | None) -> int:
    findings: list[Finding] = []
    metadata = {"workspace": str(workspace), "outdir": str(outdir)}

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
        resolved_kind = _resolve_kind(workspace, kind)
        schema = _load_fs_schema(resolved_kind)
        profiles = schema.get("profiles", {})
        resolved_profile = profile or _resolve_profile(workspace, profiles)
        if resolved_profile not in profiles:
            resolved_profile = "ms"
        metadata["kind"] = resolved_kind
        metadata["profile"] = resolved_profile
        findings.extend(_validate_fs(workspace, schema, resolved_profile))

    report = Report(
        command="validate",
        summary=build_summary(findings),
        findings=findings,
        metadata=metadata,
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
    validate_parser.add_argument("--kind", choices=["incoming", "delivery"], help="Package kind")
    validate_parser.add_argument("--profile", choices=["ms", "cle", "mscle"], help="Validation profile")

    normalize_parser = subparsers.add_parser("normalize", help="Normalize incoming package into canonical workspace")
    normalize_parser.add_argument("path", help="Path to incoming package")
    normalize_parser.add_argument("--out", required=True, help="Canonical workspace output path")
    normalize_parser.add_argument("--kind", choices=["incoming", "delivery"], default="incoming", help="Source package kind")
    normalize_parser.add_argument("--profile", choices=["ms", "cle", "mscle"], help="Workspace profile")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "ingest":
            return _ingest(Path(args.zip_path), Path(args.workspace))
        if args.command == "validate":
            return _validate(Path(args.workspace), Path(args.out), args.kind, args.profile)
        if args.command == "normalize":
            return _normalize(Path(args.path), Path(args.out), args.kind, args.profile)
    except Exception:
        traceback.print_exc()
        return 1
    return 1
