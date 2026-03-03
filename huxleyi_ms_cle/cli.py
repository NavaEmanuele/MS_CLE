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

from .build import build_delivery
from .mdb import check_relations, check_tables_required, find_mdb_files, try_read_mdb_pyodbc, write_sqlite
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


def _write_build_reports(outdir: Path, build_details: dict[str, Any]) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    json_path = outdir / "build_report.json"
    html_path = outdir / "build_report.html"
    json_path.write_text(json.dumps(build_details, ensure_ascii=True, indent=2), encoding="utf-8")

    rows = []
    for layer in build_details.get("layers", []):
        if not isinstance(layer, dict):
            continue
        rows.append(
            "<tr>"
            f"<td>{layer.get('layer_relpath', '')}</td>"
            f"<td>{layer.get('format', '')}</td>"
            f"<td>{len(layer.get('added_fields', []))}</td>"
            f"<td>{len(layer.get('renamed_fields', {})) + len(layer.get('field_name_mapping', {}))}</td>"
            f"<td>{len(layer.get('dropped_fields', []))}</td>"
            f"<td>{len(layer.get('warnings', []))}</td>"
            "</tr>"
        )
    rows_html = "\n".join(rows) if rows else "<tr><td colspan='6'>No layers processed</td></tr>"
    summary = build_details.get("summary", {})
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Build Report</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 24px; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #ccc; padding: 8px; text-align: left; }}
    th {{ background: #f4f4f4; }}
  </style>
</head>
<body>
  <h1>Build Report</h1>
  <p>Generated at: {build_details.get("generated_at", "")}</p>
  <p>Layers written: {summary.get("layers_written", 0)} | Records touched: {summary.get("records_touched", 0)} | Warnings: {summary.get("warnings", 0)}</p>
  <table>
    <thead>
      <tr><th>Layer</th><th>Format</th><th>Added</th><th>Renamed</th><th>Dropped</th><th>Warnings</th></tr>
    </thead>
    <tbody>
      {rows_html}
    </tbody>
  </table>
</body>
</html>
"""
    html_path.write_text(html, encoding="utf-8")


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
            "delivery": {"fs_schema": "fs_structure.yaml", "layers_schema": "layers.yaml", "domains_schema": "domains.yaml"},
            "incoming": {"fs_schema": "fs_structure.yaml", "layers_schema": "layers.yaml", "domains_schema": "domains.yaml"},
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
    if key == "mdb_schema":
        return {"version": 1, "databases": []}
    if key == "domains_schema":
        return {"version": 1, "domains": []}
    raise FileNotFoundError(f"No schema found for kind '{kind}' and key '{key}'")


def _load_fs_schema(kind: str) -> dict[str, Any]:
    return _load_schema_by_key(kind, "fs_schema", "fs_structure.yaml")


def _load_layers_schema(kind: str) -> dict[str, Any]:
    return _load_schema_by_key(kind, "layers_schema", "layers.yaml")


def _load_topology_schema(kind: str) -> dict[str, Any]:
    return _load_schema_by_key(kind, "topology_schema", "topology.yaml")


def _load_mdb_schema(kind: str) -> dict[str, Any]:
    return _load_schema_by_key(kind, "mdb_schema", "mdb.yaml")


def _load_domains_schema(kind: str) -> dict[str, Any]:
    return _load_schema_by_key(kind, "domains_schema", "domains.yaml")


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


def _normalize_severity(value: Any, default: str = SEVERITY_WARN) -> str:
    if not isinstance(value, str):
        return default
    normalized = value.strip().upper()
    if normalized in {SEVERITY_BLOCKER, SEVERITY_WARN, SEVERITY_INFO}:
        return normalized
    return default


def _compile_domains(domains_schema: dict[str, Any]) -> list[dict[str, Any]]:
    compiled: list[dict[str, Any]] = []
    for item in domains_schema.get("domains", []):
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        allowed_raw = item.get("allowed", [])
        allowed = {str(v) for v in allowed_raw} if isinstance(allowed_raw, list) else None
        regex_raw = item.get("regex")
        regex_compiled = None
        if isinstance(regex_raw, str) and regex_raw.strip():
            try:
                regex_compiled = re.compile(regex_raw)
            except re.error:
                regex_compiled = None
        compiled.append(
            {
                "name": name,
                "allowed": allowed,
                "regex": regex_compiled,
                "regex_raw": regex_raw,
                "severity": _normalize_severity(item.get("severity"), SEVERITY_WARN),
            }
        )
    return compiled


def _match_domain_rule(domain_name: str, compiled_domains: list[dict[str, Any]]) -> dict[str, Any] | None:
    for item in compiled_domains:
        name = item.get("name")
        if isinstance(name, str) and fnmatch(domain_name, name):
            return item
    return None


def _validate_layers(workspace: Path, layers_schema: dict[str, Any], domains_schema: dict[str, Any] | None = None) -> list[Finding]:
    findings: list[Finding] = []
    compiled_domains = _compile_domains(domains_schema or {"domains": []})
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
        field_defs = [f for f in layer.get("fields", []) if isinstance(f, dict)]

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

        for field_cfg in field_defs:
            field_name = field_cfg.get("name")
            domain_name = field_cfg.get("domain")
            if not isinstance(field_name, str) or not isinstance(domain_name, str):
                continue
            if field_name not in gdf.columns:
                continue
            rule = _match_domain_rule(domain_name, compiled_domains)
            if rule is None:
                continue

            severity = _normalize_severity(field_cfg.get("severity"), rule.get("severity", SEVERITY_WARN))
            non_null_values = gdf[field_name].dropna().tolist()

            allowed = rule.get("allowed")
            if isinstance(allowed, set) and allowed:
                invalid_allowed = [str(v) for v in non_null_values if str(v) not in allowed]
                if invalid_allowed:
                    findings.append(
                        _mk_finding(
                            "DOM010",
                            severity,
                            f"Values outside allowed domain for {field_name}: {len(invalid_allowed)}",
                            str(shp_path),
                            {
                                "layer": relpath,
                                "field": field_name,
                                "domain": domain_name,
                                "invalid_count": len(invalid_allowed),
                                "invalid_values_sample": invalid_allowed[:20],
                            },
                        )
                    )

            regex_obj = rule.get("regex")
            if regex_obj is not None:
                invalid_regex = [str(v) for v in non_null_values if regex_obj.fullmatch(str(v)) is None]
                if invalid_regex:
                    findings.append(
                        _mk_finding(
                            "DOM020",
                            severity,
                            f"Values not matching regex domain for {field_name}: {len(invalid_regex)}",
                            str(shp_path),
                            {
                                "layer": relpath,
                                "field": field_name,
                                "domain": domain_name,
                                "regex": rule.get("regex_raw"),
                                "invalid_count": len(invalid_regex),
                                "invalid_values_sample": invalid_regex[:20],
                            },
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


def _validate_topology(workspace: Path, topology_schema: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []
    defaults = topology_schema.get("defaults", {})
    default_threshold = float(defaults.get("min_overlap_area", 0.0))
    default_micro_severity = str(defaults.get("micro_overlap_severity", "WARN")).upper()

    for rule in topology_schema.get("layers", []):
        if not isinstance(rule, dict):
            continue
        if not bool(rule.get("no_overlaps", False)):
            continue
        relpath = rule.get("path")
        if not isinstance(relpath, str):
            continue

        shp_path = workspace / relpath
        if not shp_path.exists():
            continue

        try:
            gdf = gpd.read_file(shp_path)
        except Exception:
            continue

        if gdf.empty or "geometry" not in gdf.columns:
            continue
        geom_types = {str(gt).lower() for gt in gdf.geometry.geom_type.dropna().unique().tolist()}
        if not any("polygon" in gt for gt in geom_types):
            continue

        threshold = float(rule.get("min_overlap_area", default_threshold))
        micro_severity = str(rule.get("micro_overlap_severity", default_micro_severity)).upper()
        report_micro = bool(rule.get("report_micro_overlap", True))

        sindex = gdf.sindex
        for i, geom_i in enumerate(gdf.geometry):
            if geom_i is None or geom_i.is_empty:
                continue
            candidates = sindex.intersection(geom_i.bounds)
            for j in candidates:
                if j <= i:
                    continue
                geom_j = gdf.geometry.iloc[j]
                if geom_j is None or geom_j.is_empty:
                    continue
                if not geom_i.intersects(geom_j):
                    continue
                overlap = geom_i.intersection(geom_j)
                area = float(overlap.area) if not overlap.is_empty else 0.0
                if area <= 0:
                    continue
                if area > threshold:
                    findings.append(
                        _mk_finding(
                            "TOP020",
                            SEVERITY_BLOCKER,
                            f"Overlap area {area:.6f} exceeds threshold {threshold:.6f} in {relpath}",
                            str(shp_path),
                            {"layer": relpath, "index_a": int(i), "index_b": int(j), "overlap_area": area, "threshold": threshold},
                        )
                    )
                elif report_micro:
                    findings.append(
                        _mk_finding(
                            "TOP021",
                            micro_severity,
                            f"Micro-overlap area {area:.6f} below/equal threshold {threshold:.6f} in {relpath}",
                            str(shp_path),
                            {"layer": relpath, "index_a": int(i), "index_b": int(j), "overlap_area": area, "threshold": threshold},
                        )
                    )
    return findings


def _validate_mdb(workspace: Path, outdir: Path, profile: str, mdb_schema: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []
    db_entries = [d for d in mdb_schema.get("databases", []) if isinstance(d, dict)]
    # Backward compatibility for legacy single-db schema.
    if not db_entries and isinstance(mdb_schema.get("mdb_files_glob"), list):
        db_entries = [
            {
                "name": "default",
                "globs": mdb_schema.get("mdb_files_glob", []),
                "required_for_profiles": mdb_schema.get("require_mdb_for_profiles", []),
                "tables": mdb_schema.get("tables", []),
                "relations": mdb_schema.get("relations", []),
            }
        ]

    for db_cfg in db_entries:
        db_name = db_cfg.get("name")
        if not isinstance(db_name, str) or not db_name.strip():
            continue
        globs = [str(g) for g in db_cfg.get("globs", []) if isinstance(g, str)]
        if not globs:
            continue
        require_profiles = {
            str(p).lower()
            for p in db_cfg.get("required_for_profiles", [])
            if isinstance(p, str)
        }
        is_required = profile.lower() in require_profiles

        mdb_files = find_mdb_files(workspace, globs)
        if not mdb_files:
            if is_required:
                findings.append(
                    _mk_finding(
                        "MDB020",
                        SEVERITY_BLOCKER,
                        f"Required MDB database not found: {db_name}",
                        str(workspace),
                        {"database": db_name, "globs": globs},
                    )
                )
            continue

        mdb_path = mdb_files[0]
        try:
            tables = try_read_mdb_pyodbc(mdb_path)
        except Exception as exc:
            findings.append(
                _mk_finding(
                    "MDB010",
                    SEVERITY_WARN,
                    f"MDB '{db_name}' not readable via pyodbc. Install Microsoft Access Database Engine/ODBC driver.",
                    str(mdb_path),
                    {"database": db_name, "error": str(exc)},
                )
            )
            # As requested, skip relation checks when DB is not readable.
            continue

        sqlite_path = outdir / f"normalized_{db_name}.sqlite"
        write_sqlite(tables, sqlite_path)
        tables_cfg = [t for t in db_cfg.get("tables", []) if isinstance(t, dict)]
        relations_cfg = [r for r in db_cfg.get("relations", []) if isinstance(r, dict)]
        findings.extend(check_tables_required(sqlite_path, tables_cfg))
        if db_name == "cle_db":
            findings.extend(check_relations(sqlite_path, relations_cfg, workspace, tables_cfg))

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


def _copy_default_workspace_tree(source_path: Path, out_workspace: Path) -> int:
    ignore_patterns = ["tmp*", "output", "data_private", ".pytest_cache", ".tmp_pytest", "__pycache__"]
    copied = 0
    out_resolved = out_workspace.resolve()

    for current_root, dirs, files in os.walk(source_path):
        current_path = Path(current_root)
        try:
            rel_root = current_path.relative_to(source_path)
        except ValueError:
            continue

        # Do not recurse into the output workspace if it is inside the source tree.
        try:
            current_resolved = current_path.resolve()
            if current_resolved == out_resolved:
                dirs[:] = []
                continue
        except Exception:
            pass

        pruned_dirs: list[str] = []
        for dirname in dirs:
            rel_dir = str((rel_root / dirname)).replace("\\", "/")
            if any(fnmatch(dirname, pattern) or fnmatch(rel_dir, pattern) for pattern in ignore_patterns):
                continue
            pruned_dirs.append(dirname)
        dirs[:] = pruned_dirs

        for filename in files:
            src_file = current_path / filename
            rel_file = src_file.relative_to(source_path)
            dst_file = out_workspace / rel_file
            if src_file.resolve() == dst_file.resolve():
                continue
            dst_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_file, dst_file)
            copied += 1

    return copied


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

    copied_files_count = _copy_default_workspace_tree(source_path, out_workspace)

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

    moved_files_count = 0
    ms23_examples: list[dict[str, str]] = []
    for item in mapped_items:
        source = item.get("source")
        dest = item.get("dest")
        if not isinstance(source, str) or not isinstance(dest, str):
            continue
        try:
            source_rel = str(Path(source).resolve().relative_to(source_path)).replace("\\", "/")
        except Exception:
            source_rel = source.replace("\\", "/")
        try:
            dest_rel = str(Path(dest).resolve().relative_to(out_workspace.resolve())).replace("\\", "/")
        except Exception:
            dest_rel = dest.replace("\\", "/")
        if source_rel != dest_rel:
            moved_files_count += 1
        if source_rel.startswith("MS23/") and len(ms23_examples) < 10:
            ms23_examples.append({"from": source_rel, "to": dest_rel})

    workspace_manifest = {
        "source_path": str(source_path),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "kind": resolved_kind,
        "profile": resolved_profile,
        "created_dirs": created_dirs,
        "copied_files_count": copied_files_count,
        "moved_files_count": moved_files_count,
        "ms23_to_ms2_examples": ms23_examples,
        "mapped_items": mapped_items,
    }
    (out_workspace / "workspace_manifest.json").write_text(
        json.dumps(workspace_manifest, ensure_ascii=True, indent=2),
        encoding="utf-8",
    )
    return 0


def _build(
    workspace: Path,
    outdir: Path,
    kind: str | None,
    profile: str | None,
    fmt: str,
    zip_path: Path | None,
) -> int:
    findings: list[Finding] = []
    metadata: dict[str, Any] = {"workspace": str(workspace), "outdir": str(outdir), "kind": kind or "delivery", "format": fmt}
    if kind == "incoming":
        findings.append(
            _mk_finding(
                "BLD000",
                SEVERITY_WARN,
                "Build currently targets delivery layout; incoming kind is accepted but treated as delivery output.",
                str(workspace),
            )
        )

    status, build_findings, build_meta = build_delivery(workspace, outdir, profile, fmt, zip_path)
    findings.extend(build_findings)
    metadata.update(build_meta)

    report = Report(
        command="build",
        summary=build_summary(findings),
        findings=findings,
        metadata=metadata,
    )
    _write_reports(outdir, report)
    build_details = metadata.get("build_details")
    if isinstance(build_details, dict):
        _write_build_reports(outdir, build_details)
    return status


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
        domains_schema = _load_domains_schema(resolved_kind)
        findings.extend(_validate_layers(workspace, layers_schema, domains_schema))
        topology_schema = _load_topology_schema(resolved_kind)
        findings.extend(_validate_topology(workspace, topology_schema))
        mdb_schema = _load_mdb_schema(resolved_kind)
        findings.extend(_validate_mdb(workspace, outdir, resolved_profile, mdb_schema))

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

    build_parser = subparsers.add_parser("build", help="Build delivery package from canonical workspace")
    build_parser.add_argument("workspace", help="Canonical workspace path")
    build_parser.add_argument("--out", required=True, help="Output delivery directory")
    build_parser.add_argument("--kind", choices=["incoming", "delivery"], help="Workspace kind")
    build_parser.add_argument("--profile", choices=["ms", "cle", "mscle"], help="Build profile")
    build_parser.add_argument("--format", choices=["shp", "gpkg", "both"], default="shp", help="Output layer format")
    build_parser.add_argument("--zip", dest="zip_path", help="Optional zip path for final package")

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
        if args.command == "build":
            zip_path = Path(args.zip_path) if getattr(args, "zip_path", None) else None
            return _build(Path(args.workspace), Path(args.out), args.kind, args.profile, args.format, zip_path)
        if args.command == "scan":
            return _scan_workspace(Path(args.workspace), Path(args.out))
    except Exception:
        traceback.print_exc()
        return 1
    return 1
