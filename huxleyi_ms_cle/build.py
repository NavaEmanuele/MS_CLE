from __future__ import annotations

import json
import os
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
import yaml

from .reporting import Finding


def _schemas_root() -> Path:
    override = os.getenv("HUXLEYI_SCHEMAS_ROOT")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[1] / "schemas"


def _load_yaml(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Invalid YAML format: {path}")
    return payload


def _resolve_profile(workspace: Path, fs_schema: dict[str, Any], profile: str | None) -> str:
    if profile and profile in fs_schema.get("profiles", {}):
        return profile
    manifest = workspace / "manifest.json"
    if manifest.exists():
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            candidate = payload.get("estimated_profile")
            if isinstance(candidate, str) and candidate in fs_schema.get("profiles", {}):
                return candidate
        except json.JSONDecodeError:
            pass
    return "ms"


def _finding(check_id: str, severity: str, message: str, location: str | None = None, details: dict[str, Any] | None = None) -> Finding:
    return Finding(
        code=check_id,
        check_id=check_id,
        severity=severity,
        message=message,
        location=location,
        details=details,
    )


def load_build_actions() -> dict[str, Any]:
    path = _schemas_root() / "delivery" / "build_actions.yaml"
    if not path.exists():
        return {"version": 1, "actions": []}
    return _load_yaml(path)


def _load_layers_schema() -> dict[str, Any]:
    root = _schemas_root() / "delivery"
    minimal = root / "layers_minimal.yaml"
    full = root / "layers.yaml"
    if minimal.exists():
        return _load_yaml(minimal)
    if full.exists():
        return _load_yaml(full)
    return {"version": 1, "layers": []}


def _load_fs_schema() -> dict[str, Any]:
    candidate = _schemas_root() / "delivery" / "fs_structure.yaml"
    if candidate.exists():
        return _load_yaml(candidate)
    return {"profiles": {"ms": {"required_dirs": []}, "cle": {"required_dirs": []}, "mscle": {"required_dirs": []}}}


def _resolve_dict(path_value: str | None) -> dict[str, Any]:
    if not path_value:
        return {}
    path = Path(path_value)
    candidates: list[Path] = []
    if path.is_absolute():
        candidates.append(path)
    else:
        project_root = Path(__file__).resolve().parents[1]
        candidates.append(project_root / path)
        if len(path.parts) > 1 and path.parts[0].lower() == "schemas":
            candidates.append(_schemas_root() / Path(*path.parts[1:]))
        candidates.append(_schemas_root() / path)

    payload = None
    for candidate in candidates:
        if candidate.exists():
            payload = _load_yaml(candidate)
            break
    if payload is None:
        return {}

    mappings = payload.get("mappings")
    if isinstance(mappings, dict):
        return mappings
    return payload


def _normalize_record(row: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in row.items():
        out[key] = "" if pd.isna(value) else value
    return out


def _expr_template(df: gpd.GeoDataFrame, template: str) -> list[str]:
    values: list[str] = []
    for row in df.to_dict(orient="records"):
        normalized = _normalize_record(row)
        try:
            values.append(str(template).format(**normalized))
        except Exception:
            values.append(str(template))
    return values


def _expr_concat(df: gpd.GeoDataFrame, fields: list[str], sep: str) -> list[str]:
    values: list[str] = []
    for _, row in df.iterrows():
        parts = []
        for field in fields:
            value = row[field] if field in df.columns else ""
            parts.append("" if pd.isna(value) else str(value))
        values.append(sep.join(parts))
    return values


def _expr_from_dict(df: gpd.GeoDataFrame, mapping: dict[str, Any], source_field: str, default_template: str = "Tipo {code}") -> list[str]:
    values: list[str] = []
    normalized_map = {str(k).upper(): str(v) for k, v in mapping.items()}
    for code in df[source_field] if source_field in df.columns else [None] * len(df):
        key = "" if pd.isna(code) else str(code).strip().upper()
        values.append(normalized_map.get(key, default_template.format(code=key)))
    return values


def _stable_shp_name(original: str, used_upper: set[str]) -> str:
    base = original[:10]
    candidate = base
    idx = 1
    while candidate.upper() in used_upper:
        suffix = str(idx)
        candidate = f"{base[: 10 - len(suffix)]}{suffix}"
        idx += 1
    return candidate


def _truncate_shp_fields(gdf: gpd.GeoDataFrame) -> tuple[gpd.GeoDataFrame, dict[str, str], list[str]]:
    geometry_name = gdf.geometry.name
    mapping: dict[str, str] = {}
    warnings: list[str] = []
    used_upper: set[str] = set()

    for col in gdf.columns:
        if col == geometry_name:
            continue
        name = str(col)
        candidate = name
        if len(name) > 10:
            candidate = _stable_shp_name(name, used_upper)
            mapping[name] = candidate
            warnings.append(f"Field '{name}' truncated to '{candidate}' for SHP output")
        elif name.upper() in used_upper:
            candidate = _stable_shp_name(name, used_upper)
            mapping[name] = candidate
            warnings.append(f"Field '{name}' renamed to '{candidate}' for SHP uniqueness")
        used_upper.add(candidate.upper())

    if mapping:
        gdf = gdf.rename(columns=mapping)
    return gdf, mapping, warnings


def _enforce_string_lengths(
    gdf: gpd.GeoDataFrame,
    field_specs: dict[str, dict[str, Any]],
) -> tuple[gpd.GeoDataFrame, list[dict[str, Any]], list[str]]:
    truncations: list[dict[str, Any]] = []
    warnings: list[str] = []
    for field, spec in field_specs.items():
        if field not in gdf.columns:
            continue
        if str(spec.get("type", "")).lower() not in {"str", "string", "text"}:
            continue
        length = spec.get("length")
        if not isinstance(length, int) or length <= 0:
            continue

        series = gdf[field].astype(object)
        affected = 0
        converted = []
        for value in series:
            if pd.isna(value):
                converted.append(value)
                continue
            sval = str(value)
            if len(sval) > length:
                converted.append(sval[:length])
                affected += 1
            else:
                converted.append(sval)
        if affected > 0:
            gdf[field] = converted
            truncations.append({"field": field, "max_length": length, "affected_rows": affected})
            warnings.append(f"Field '{field}' truncated to max length {length} for {affected} rows")
    return gdf, truncations, warnings


def _collect_field_specs(action: dict[str, Any]) -> dict[str, dict[str, Any]]:
    specs: dict[str, dict[str, Any]] = {}
    for item in action.get("add_fields", []):
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if isinstance(name, str):
            specs[name] = dict(item)
    return specs


def apply_actions(
    layer_path_in: Path,
    layer_path_out: Path,
    action: dict[str, Any],
) -> tuple[gpd.GeoDataFrame, list[Finding], dict[str, Any]]:
    gdf = gpd.read_file(layer_path_in)
    findings: list[Finding] = []

    dict_payload = _resolve_dict(action.get("dict"))
    dict_mapping = dict_payload.get("mapping", dict_payload)
    if not isinstance(dict_mapping, dict):
        dict_mapping = {}

    layer_stats: dict[str, Any] = {
        "layer_in": str(layer_path_in),
        "layer_out": str(layer_path_out),
        "records_in": int(len(gdf)),
        "records_out": int(len(gdf)),
        "added_fields": [],
        "renamed_fields": {},
        "dropped_fields": [],
        "set_values": [],
        "field_name_mapping": {},
        "string_truncations": [],
        "warnings": [],
    }

    # 1) rename_fields
    rename_fields = action.get("rename_fields", {})
    if isinstance(rename_fields, dict):
        safe_map = {str(k): str(v) for k, v in rename_fields.items() if str(k) in gdf.columns and str(k) != gdf.geometry.name}
        if safe_map:
            gdf = gdf.rename(columns=safe_map)
            layer_stats["renamed_fields"].update(safe_map)

    # 2) add_fields
    field_specs = _collect_field_specs(action)
    for field_name in field_specs:
        if field_name not in gdf.columns:
            gdf[field_name] = None
            layer_stats["added_fields"].append(field_name)

    # 3) set_values
    for assignment in action.get("set_values", []):
        if not isinstance(assignment, dict):
            continue
        target = assignment.get("field")
        expr = assignment.get("expr")
        if not isinstance(target, str) or not isinstance(expr, str):
            continue
        if target not in gdf.columns:
            gdf[target] = None
            layer_stats["added_fields"].append(target)

        touched = 0
        if expr in {"template", "url_template"}:
            template = assignment.get("template") or action.get("url_template") or ""
            values = _expr_template(gdf, str(template))
            gdf[target] = values
            touched = len(values)
        elif expr == "concat":
            fields = assignment.get("fields", [])
            if not isinstance(fields, list):
                fields = []
            fields = [str(f) for f in fields]
            sep = str(assignment.get("sep", ""))
            values = _expr_concat(gdf, fields, sep)
            gdf[target] = values
            touched = len(values)
        elif expr in {"dict", "descr_from_dict"}:
            source_field = str(assignment.get("source_field") or action.get("source_field") or "cod")
            default_template = str(assignment.get("default") or "Tipo {code}")
            values = _expr_from_dict(gdf, dict_mapping, source_field, default_template)
            gdf[target] = values
            touched = len(values)
        elif expr.startswith("literal:"):
            value = expr.split("literal:", 1)[1]
            gdf[target] = value
            touched = len(gdf)
        elif expr.startswith("copy:"):
            source_field = expr.split("copy:", 1)[1]
            if source_field in gdf.columns:
                gdf[target] = gdf[source_field]
                touched = len(gdf)

        if touched > 0:
            layer_stats["set_values"].append({"field": target, "expr": expr, "records_touched": touched})

    # 4) drop_fields
    geometry_name = gdf.geometry.name
    drop_fields = [str(f) for f in action.get("drop_fields", []) if isinstance(f, str)]
    valid_drop = [f for f in drop_fields if f in gdf.columns and f != geometry_name]
    if valid_drop:
        gdf = gdf.drop(columns=valid_drop)
        layer_stats["dropped_fields"].extend(valid_drop)

    # 5) Shapefile constraints
    if layer_path_out.suffix.lower() == ".shp":
        gdf, shp_map, shp_warnings = _truncate_shp_fields(gdf)
        if shp_map:
            layer_stats["field_name_mapping"].update(shp_map)
            for msg in shp_warnings:
                findings.append(_finding("BLD020", "WARN", msg, str(layer_path_out), {"field_name_mapping": shp_map}))
                layer_stats["warnings"].append(msg)

        # Rebind specs after potential renames.
        rebased_specs: dict[str, dict[str, Any]] = {}
        for key, spec in field_specs.items():
            rebased_specs[shp_map.get(key, key)] = spec
        gdf, truncations, len_warnings = _enforce_string_lengths(gdf, rebased_specs)
        if truncations:
            layer_stats["string_truncations"].extend(truncations)
            for msg in len_warnings:
                findings.append(_finding("BLD021", "WARN", msg, str(layer_path_out), {"truncations": truncations}))
                layer_stats["warnings"].append(msg)

    layer_stats["records_out"] = int(len(gdf))
    return gdf, findings, layer_stats


def write_output(gdf: gpd.GeoDataFrame, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if out_path.suffix.lower() == ".gpkg":
        gdf.to_file(out_path, layer=out_path.stem, driver="GPKG")
    else:
        gdf.to_file(out_path, driver="ESRI Shapefile")


def _zip_output(outdir: Path, zip_path: Path) -> None:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    skip_names = {"report.json", "report.html", "build_report.json", "build_report.html"}
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in outdir.rglob("*"):
            if path.is_file() and path.name not in skip_names:
                zf.write(path, arcname=str(path.relative_to(outdir)).replace("\\", "/"))


def _action_for_layer(actions: list[dict[str, Any]], rel_layer_path: str) -> dict[str, Any]:
    for action in actions:
        if isinstance(action, dict) and action.get("layer") == rel_layer_path:
            return action
    return {}


def build_delivery(
    workspace: Path,
    outdir: Path,
    profile: str | None,
    fmt: str,
    zip_path: Path | None = None,
) -> tuple[int, list[Finding], dict[str, Any]]:
    findings: list[Finding] = []
    metadata: dict[str, Any] = {"workspace": str(workspace), "outdir": str(outdir), "format": fmt}
    build_details: dict[str, Any] = {
        "version": 1,
        "workspace": str(workspace),
        "outdir": str(outdir),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "layers": [],
        "summary": {
            "layers_written": 0,
            "records_touched": 0,
            "warnings": 0,
            "added_fields": 0,
            "renamed_fields": 0,
            "dropped_fields": 0,
        },
    }

    if not workspace.exists():
        findings.append(_finding("BLD001", "BLOCKER", f"Workspace does not exist: {workspace}", str(workspace)))
        metadata["build_details"] = build_details
        return 2, findings, metadata

    fs_schema = _load_fs_schema()
    resolved_profile = _resolve_profile(workspace, fs_schema, profile)
    metadata["profile"] = resolved_profile

    outdir.mkdir(parents=True, exist_ok=True)
    for dirname in fs_schema.get("profiles", {}).get(resolved_profile, {}).get("required_dirs", []):
        (outdir / str(dirname)).mkdir(parents=True, exist_ok=True)

    layers_schema = _load_layers_schema()
    actions_payload = load_build_actions()
    actions = actions_payload.get("actions", [])
    if not isinstance(actions, list):
        actions = []

    for layer in layers_schema.get("layers", []):
        if not isinstance(layer, dict):
            continue
        rel = layer.get("path")
        if not isinstance(rel, str):
            continue
        rel_norm = rel.replace("\\", "/")
        src = workspace / rel_norm
        if not src.exists():
            findings.append(_finding("BLD002", "BLOCKER", f"Layer missing in workspace: {rel_norm}", str(src)))
            continue

        action = _action_for_layer(actions, rel_norm)
        output_paths: list[Path] = []
        if fmt in {"shp", "both"}:
            output_paths.append(outdir / rel_norm)
        if fmt in {"gpkg", "both"}:
            output_paths.append((outdir / rel_norm).with_suffix(".gpkg"))

        for output_path in output_paths:
            gdf, action_findings, layer_stats = apply_actions(src, output_path, action)
            findings.extend(action_findings)
            write_output(gdf, output_path)
            layer_stats["format"] = output_path.suffix.lower().lstrip(".")
            layer_stats["layer_relpath"] = str(output_path.relative_to(outdir)).replace("\\", "/")
            build_details["layers"].append(layer_stats)
            build_details["summary"]["layers_written"] += 1
            build_details["summary"]["records_touched"] += sum(
                int(item.get("records_touched", 0)) for item in layer_stats.get("set_values", [])
            )
            build_details["summary"]["warnings"] += len(layer_stats.get("warnings", []))
            build_details["summary"]["added_fields"] += len(layer_stats.get("added_fields", []))
            build_details["summary"]["renamed_fields"] += len(layer_stats.get("renamed_fields", {})) + len(
                layer_stats.get("field_name_mapping", {})
            )
            build_details["summary"]["dropped_fields"] += len(layer_stats.get("dropped_fields", []))

    metadata["layers_written"] = build_details["summary"]["layers_written"]
    metadata["build_details"] = build_details

    if zip_path is not None:
        _zip_output(outdir, zip_path)
        metadata["zip_path"] = str(zip_path)

    has_blocker = any(f.severity == "BLOCKER" for f in findings)
    return (2 if has_blocker else 0), findings, metadata
