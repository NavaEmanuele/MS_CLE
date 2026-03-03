from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import traceback
import uuid
import zipfile
from datetime import datetime, timezone
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

import geopandas as gpd
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


def _copy_path_to_dest(src: Path, dst: Path) -> str:
    if src.is_dir():
        shutil.copytree(src, dst, dirs_exist_ok=True)
    else:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    return str(dst)


def _write_reports(outdir: Path, report: Report) -> None:
    write_report_json(report, outdir / "report.json")
    write_report_html(report, outdir / "report.html")


def _load_yaml(path: Path) -> dict[str, Any]:
    content = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(content, dict):
        raise ValueError(f"Invalid YAML schema format: {path}")
    return content


def _schemas_root() -> Path:
    override = os.getenv("HUXLEYI_SCHEMAS_ROOT")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[1] / "schemas"


def _load_catalog() -> dict[str, Any]:
    catalog_path = _schemas_root() / "catalog.yaml"
    if catalog_path.exists():
        return _load_yaml(catalog_path)
    return {
        "kinds": {
            "delivery": {"fs_schema": "fs_structure.yaml", "layers_schema": "layers.yaml"},
            "incoming": {"fs_schema": "fs_structure.yaml", "layers_schema": "layers.yaml"},
        }
    }


def _load_schema_by_key(kind: str, key: str, fallback_name: str) -> dict[str, Any]:
    root = _schemas_root()
    catalog = _load_catalog()
    kind_cfg = catalog.get("kinds", {}).get(kind, {})
    rel = kind_cfg.get(key)
    candidates: list[Path] = []
    if isinstance(rel, str):
        candidates.append(root / rel)
    candidates.append(root / kind / fallback_name)
    legacy = root / fallback_name
    if legacy.exists():
        candidates.append(legacy)
    for candidate in candidates:
        if candidate.exists():
            return _load_yaml(candidate)
    if key == "layers_schema":
        return {"version": 1, "layers": []}
    raise FileNotFoundError(f"No schema found for kind '{kind}' and key '{key}'")


def _load_fs_schema(kind: str) -> dict[str, Any]:
    return _load_schema_by_key(kind, "fs_schema", "fs_structure.yaml")


def _load_layers_schema(kind: str) -> dict[str, Any]:
    return _load_schema_by_key(kind, "layers_schema", "layers.yaml")


def _load_mappings_schema() -> dict[str, Any]:
    root = _schemas_root()
    catalog = _load_catalog()
    rel = catalog.get("kinds", {}).get("incoming", {}).get("mappings")
    candidates: list[Path] = []
    if isinstance(rel, str):
        candidates.append(root / rel)
    candidates.append(root / "incoming" / "mappings.yaml")
    for candidate in candidates:
        if candidate.exists():
            return _load_yaml(candidate)
    return {"mappings": []}


def _detect_profile_from_workspace(workspace: Path) -> str:
    top_dirs = {item.name.lower() for item in workspace.iterdir() if item.is_dir()}
    has_cle = "cle" in top_dirs or any(workspace.glob("CLE/**/*.mdb"))
    has_ms = any(name in top_dirs for name in {"ms1", "ms2", "ms23", "geotec", "indagini"}) or any(
        workspace.glob("MS1/**/*.shp")
    )
    if has_cle and has_ms:
        return "mscle"
    if has_cle:
        return "cle"
    return "ms"


def _resolve_profile(workspace: Path, profiles: dict[str, Any]) -> str:
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


def _mk_finding(
    check_id: str,
    severity: str,
    message: str,
    location: str | None = None,
    details: dict[str, Any] | None = None,
) -> Finding:
    return Finding(
        code=check_id,
        check_id=check_id,
        severity=severity,
        message=message,
        location=location,
        details=details,
    )


def _validate_fs(workspace: Path, schema: dict[str, Any], profile: str) -> list[Finding]:
    findings: list[Finding] = []
    profile_cfg = schema.get("profiles", {}).get(profile, {})
    required_dirs = profile_cfg.get("required_dirs", [])
    required_files_glob = profile_cfg.get("required_files_glob", [])

    for required_dir in required_dirs:
        required_path = workspace / required_dir
        if not required_path.exists() or not required_path.is_dir():
            findings.append(
                _mk_finding(
                    "FS001",
                    SEVERITY_BLOCKER,
                    f"Required directory missing: {required_dir}",
                    str(required_path),
                    {"required_dir": required_dir, "profile": profile},
                )
            )

    for pattern in required_files_glob:
        matches = [p for p in workspace.glob(pattern) if p.is_file()]
        if not matches:
            findings.append(
                _mk_finding(
                    "FS002",
                    SEVERITY_BLOCKER,
                    f"Required file pattern not found: {pattern}",
                    str(workspace),
                    {"pattern": pattern, "profile": profile},
                )
            )

    warn_on_extra_dirs = bool(schema.get("warn_on_extra_dirs", False))
    ignore_patterns = schema.get("ignore_dirs_glob", [])
    if warn_on_extra_dirs:
        required_top = {str(d).split("/")[0] for d in required_dirs}
        actual_top = [entry for entry in workspace.iterdir() if entry.is_dir()]
        for entry in actual_top:
            name = entry.name
            rel = str(entry.relative_to(workspace)).replace("\\", "/")
            if name in required_top:
                continue
            if any(fnmatch(name, ignore) or fnmatch(rel, ignore) for ignore in ignore_patterns):
                continue
            findings.append(
                _mk_finding(
                    "FS100",
                    SEVERITY_WARN,
                    f"Extra directory found: {name}",
                    str(entry),
                    {"directory": name, "profile": profile},
                )
            )

    return findings


def _candidate_id_columns(columns: list[str]) -> list[str]:
    out: list[str] = []
    for col in columns:
        up = col.upper()
        if up.startswith("ID") or "ID_" in up:
            out.append(col)
    return out


def _scan_layers(workspace: Path) -> list[dict[str, Any]]:
    shp_paths = sorted(path for path in workspace.rglob("*.shp") if path.is_file())
    layers: list[dict[str, Any]] = []
    for shp_path in shp_paths:
        gdf = gpd.read_file(shp_path)
        columns = [str(col) for col in gdf.columns]
        inferred_dtypes = {str(col): str(dtype) for col, dtype in gdf.dtypes.items()}
        null_count = {str(col): int(gdf[col].isna().sum()) for col in gdf.columns}
        duplicate_count = {
            col: int(gdf[col].duplicated(keep=False).sum())
            for col in _candidate_id_columns(columns)
        }
        bounds = [float(value) for value in gdf.total_bounds.tolist()] if len(gdf) > 0 else None
        crs_value = str(gdf.crs) if gdf.crs is not None else None
        layers.append(
            {
                "relpath": str(shp_path.relative_to(workspace)).replace("\\", "/"),
                "columns": columns,
                "inferred_dtypes": inferred_dtypes,
                "n_records": int(len(gdf)),
                "crs": crs_value,
                "bounds": bounds,
                "null_count": null_count,
                "duplicate_count": duplicate_count,
            }
        )
    return layers


def _scan_workspace(workspace: Path, out_json: Path) -> int:
    if not workspace.exists() or not workspace.is_dir():
        raise FileNotFoundError(f"Workspace does not exist: {workspace}")
    payload = {
        "version": 1,
        "workspace": str(workspace),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "layers": _scan_layers(workspace),
    }
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    return 0


def _validate_layers(workspace: Path, layers_schema: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []
    for layer in layers_schema.get("layers", []):
        if not isinstance(layer, dict):
            continue
        relpath = layer.get("path")
        if not isinstance(relpath, str) or not relpath.strip():
            continue
        shp_path = workspace / relpath
        if not shp_path.exists():
            findings.append(
                _mk_finding(
                    "SHP001",
                    SEVERITY_BLOCKER,
                    f"Layer missing: {relpath}",
                    str(shp_path),
                )
            )
            continue
        try:
            gdf = gpd.read_file(shp_path)
        except Exception as exc:
            findings.append(
                _mk_finding(
                    "SHP001",
                    SEVERITY_BLOCKER,
                    f"Layer read failed: {relpath}",
                    str(shp_path),
                    {"error": str(exc)},
                )
            )
            continue

        required_fields = [f for f in layer.get("required_fields", []) if isinstance(f, str)]
        not_null_fields = [f for f in layer.get("not_null_fields", []) if isinstance(f, str)]
        unique_fields = [f for f in layer.get("unique_fields", []) if isinstance(f, str)]

        for field in required_fields:
            if field not in gdf.columns:
                findings.append(
                    _mk_finding(
                        "SHP010",
                        SEVERITY_BLOCKER,
                        f"Required field missing: {field}",
                        str(shp_path),
                        {"layer": relpath, "field": field},
                    )
                )

        for field in not_null_fields:
            if field in gdf.columns:
                nulls = int(gdf[field].isna().sum())
                if nulls > 0:
                    findings.append(
                        _mk_finding(
                            "SHP020",
                            SEVERITY_WARN,
                            f"Null values in field {field}: {nulls}",
                            str(shp_path),
                            {"layer": relpath, "field": field, "null_count": nulls},
                        )
                    )

        for field in unique_fields:
            if field in gdf.columns:
                duplicates = int(gdf[field].duplicated(keep=False).sum())
                if duplicates > 0:
                    findings.append(
                        _mk_finding(
                            "SHP030",
                            SEVERITY_WARN,
                            f"Duplicate values in field {field}: {duplicates}",
                            str(shp_path),
                            {"layer": relpath, "field": field, "duplicate_count": duplicates},
                        )
                    )

        if "geometry" in gdf.columns:
            invalid_mask = ~gdf.geometry.is_valid.fillna(False)
            invalid_count = int(invalid_mask.sum())
            if invalid_count > 0:
                findings.append(
                    _mk_finding(
                        "GEO010",
                        SEVERITY_BLOCKER,
                        f"Invalid geometries found: {invalid_count}",
                        str(shp_path),
                        {"layer": relpath, "invalid_count": invalid_count},
                    )
                )

        expected_epsg = layer.get("crs_epsg")
        if isinstance(expected_epsg, int):
            actual_epsg = gdf.crs.to_epsg() if gdf.crs is not None else None
            if actual_epsg != expected_epsg:
                findings.append(
                    _mk_finding(
                        "CRS010",
                        SEVERITY_WARN,
                        f"CRS mismatch. Expected EPSG:{expected_epsg}, found {actual_epsg}",
                        str(shp_path),
                        {"layer": relpath, "expected_epsg": expected_epsg, "actual_epsg": actual_epsg},
                    )
                )

    return findings


def _ingest(zip_path: Path, workspace: Path) -> int:
    findings: list[Finding] = []
    workspace.mkdir(parents=True, exist_ok=True)

    if not zip_path.exists():
        findings.append(
            _mk_finding(
                "ZIP_NOT_FOUND",
                SEVERITY_BLOCKER,
                f"Zip file not found: {zip_path}",
                str(zip_path),
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
        source_root = top_level[0] if len(top_level) == 1 and top_level[0].is_dir() else temp_root
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
        _mk_finding(
            "INGEST_COMPLETED",
            SEVERITY_INFO,
            f"Ingest completed. Extracted {len(main_files)} files (top 200 listed in manifest).",
            str(workspace),
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


def _glob_prefix(source_glob: str) -> str:
    wildcard = re.search(r"[\*\?\[]", source_glob)
    if not wildcard:
        return source_glob.strip("/\\")
    prefix = source_glob[: wildcard.start()].rstrip("/\\")
    return prefix


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
    mapped_items: list[dict[str, Any]] = []
    mappings = mappings_schema.get("mappings", [])
    if isinstance(mappings, list):
        for mapping in mappings:
            if not isinstance(mapping, dict):
                continue
            source_glob = mapping.get("source_glob")
            dest_rel = mapping.get("dest")
            if not isinstance(source_glob, str) or not isinstance(dest_rel, str):
                continue
            prefix = _glob_prefix(source_glob)
            base = source_path / prefix if prefix else source_path
            for matched in source_path.glob(source_glob):
                if matched.is_dir():
                    continue
                if prefix and base.exists():
                    try:
                        relative = matched.relative_to(base)
                    except ValueError:
                        relative = Path(matched.name)
                else:
                    relative = Path(matched.name)
                target = out_workspace / dest_rel / relative
                copied_to = _copy_path_to_dest(matched, target)
                mapped_items.append(
                    {
                        "source": str(matched),
                        "dest": copied_to,
                        "source_glob": source_glob,
                        "mapping_dest": dest_rel,
                        "transformation": f"{prefix or '.'} -> {dest_rel}",
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
    metadata: dict[str, Any] = {"workspace": str(workspace), "outdir": str(outdir)}

    if not workspace.exists():
        findings.append(
            _mk_finding(
                "WORKSPACE_NOT_FOUND",
                SEVERITY_BLOCKER,
                f"Workspace does not exist: {workspace}",
                str(workspace),
            )
        )
    else:
        resolved_kind = _resolve_kind(workspace, kind)
        fs_schema = _load_fs_schema(resolved_kind)
        profiles = fs_schema.get("profiles", {})
        resolved_profile = profile or _resolve_profile(workspace, profiles)
        if resolved_profile not in profiles:
            resolved_profile = "ms"
        metadata["kind"] = resolved_kind
        metadata["profile"] = resolved_profile
        findings.extend(_validate_fs(workspace, fs_schema, resolved_profile))
        layers_schema = _load_layers_schema(resolved_kind)
        findings.extend(_validate_layers(workspace, layers_schema))

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

    validate_parser = subparsers.add_parser("validate", help="Run validation on a workspace")
    validate_parser.add_argument("workspace", help="Workspace directory")
    validate_parser.add_argument("--out", required=True, help="Output directory for reports")
    validate_parser.add_argument("--kind", choices=["incoming", "delivery"], help="Package kind")
    validate_parser.add_argument("--profile", choices=["ms", "cle", "mscle"], help="Validation profile")

    normalize_parser = subparsers.add_parser("normalize", help="Normalize incoming package into canonical workspace")
    normalize_parser.add_argument("path", help="Path to incoming package")
    normalize_parser.add_argument("--out", required=True, help="Canonical workspace output path")
    normalize_parser.add_argument("--kind", choices=["incoming", "delivery"], default="incoming", help="Source package kind")
    normalize_parser.add_argument("--profile", choices=["ms", "cle", "mscle"], help="Workspace profile")

    scan_parser = subparsers.add_parser("scan", help="Scan workspace shapefiles and output layer metadata")
    scan_parser.add_argument("workspace", help="Workspace directory to scan")
    scan_parser.add_argument("--out", required=True, help="Output JSON path")
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
        if args.command == "scan":
            return _scan_workspace(Path(args.workspace), Path(args.out))
    except Exception:
        traceback.print_exc()
        return 1
    return 1
