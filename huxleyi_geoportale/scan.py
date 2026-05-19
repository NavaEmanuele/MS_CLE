"""First-level scanner for MS/CLE Geoportale File Geodatabases.

The scanner is conservative: it reads local datasets and writes CSV reports,
without modifying any geodatabase or source file.
"""

from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import geopandas as gpd
import pandas as pd
import pyogrio
from shapely.geometry.base import BaseGeometry

from .config import ScanConfig, load_config


@dataclass(frozen=True)
class ScanResult:
    output_dir: Path
    layer_count: int
    warning_count: int


def _write_csv(path: Path, rows: Iterable[dict]) -> int:
    rows = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return 0
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def _safe_bounds(gdf: gpd.GeoDataFrame) -> tuple[float | None, float | None, float | None, float | None]:
    if gdf.empty or gdf.geometry.is_empty.all():
        return (None, None, None, None)
    minx, miny, maxx, maxy = gdf.total_bounds
    return (float(minx), float(miny), float(maxx), float(maxy))


def _epsg(gdf: gpd.GeoDataFrame) -> int | None:
    if gdf.crs is None:
        return None
    try:
        return gdf.crs.to_epsg()
    except Exception:
        return None


def _looks_outside_lombardia(bounds: tuple[float | None, float | None, float | None, float | None], cfg: ScanConfig) -> bool:
    minx, miny, maxx, maxy = bounds
    if None in bounds:
        return False
    return bool(maxx < cfg.lombardia_minx or minx > cfg.lombardia_maxx or maxy < cfg.lombardia_miny or miny > cfg.lombardia_maxy)


def _geometry_hash(geom: BaseGeometry | None) -> str | None:
    if geom is None or geom.is_empty:
        return None
    return hashlib.sha256(geom.wkb).hexdigest()


def _candidate_comune_field(columns: list[str]) -> str | None:
    preferred = ["COMUNE", "Comune", "comune", "NOME_COM", "NOME_COMUNE", "denom_com", "DENOM_COM"]
    for name in preferred:
        if name in columns:
            return name
    for column in columns:
        if "com" in column.lower() and gpd.pd.api.types.is_object_dtype(column):
            return column
    return None


def _candidate_objectid_field(columns: list[str]) -> str | None:
    for name in ["OBJECTID", "ObjectID", "FID", "OID", "ID"]:
        if name in columns:
            return name
    return None


def _read_layer(dataset_path: Path, layer_name: str) -> gpd.GeoDataFrame:
    return gpd.read_file(dataset_path, layer=layer_name, engine="pyogrio")


def _scan_layer(cfg: ScanConfig, dataset_name: str, dataset_kind: str, dataset_path: Path, layer_name: str) -> tuple[list[dict], list[dict], list[dict], list[dict], list[dict], list[dict]]:
    inventory_rows: list[dict] = []
    field_rows: list[dict] = []
    geometry_rows: list[dict] = []
    coord_rows: list[dict] = []
    duplicate_rows: list[dict] = []
    attribute_rows: list[dict] = []

    gdf = _read_layer(dataset_path, layer_name)
    epsg = _epsg(gdf)
    bounds = _safe_bounds(gdf)
    out_of_bounds = _looks_outside_lombardia(bounds, cfg)

    inventory_rows.append(
        {
            "dataset": dataset_name,
            "kind": dataset_kind,
            "path": str(dataset_path),
            "layer": layer_name,
            "feature_count": int(len(gdf)),
            "geometry_type": str(gdf.geom_type.dropna().unique().tolist()),
            "epsg": epsg,
            "minx": bounds[0],
            "miny": bounds[1],
            "maxx": bounds[2],
            "maxy": bounds[3],
            "outside_lombardia_bounds": out_of_bounds,
        }
    )

    for column in gdf.columns:
        if column == gdf.geometry.name:
            continue
        series = gdf[column]
        field_rows.append(
            {
                "dataset": dataset_name,
                "kind": dataset_kind,
                "layer": layer_name,
                "field": column,
                "dtype": str(series.dtype),
                "null_count": int(series.isna().sum()),
                "unique_count": int(series.nunique(dropna=True)),
            }
        )

    oid_field = _candidate_objectid_field(list(gdf.columns))
    comune_field = _candidate_comune_field(list(gdf.columns))

    if epsg != cfg.expected_epsg:
        attribute_rows.append(
            {
                "dataset": dataset_name,
                "kind": dataset_kind,
                "layer": layer_name,
                "feature_id": None,
                "field": "CRS",
                "value": epsg,
                "issue": f"Expected EPSG:{cfg.expected_epsg}",
                "severity": "BLOCKER" if epsg is None else "WARNING",
            }
        )

    invalid_mask = ~gdf.geometry.is_valid.fillna(False)
    for idx, row in gdf.loc[invalid_mask].iterrows():
        geometry_rows.append(
            {
                "dataset": dataset_name,
                "kind": dataset_kind,
                "layer": layer_name,
                "feature_id": row.get(oid_field, idx) if oid_field else idx,
                "comune": row.get(comune_field) if comune_field else None,
                "issue": "Invalid geometry",
                "severity": "BLOCKER",
            }
        )

    if out_of_bounds:
        coord_rows.append(
            {
                "dataset": dataset_name,
                "kind": dataset_kind,
                "layer": layer_name,
                "feature_id": None,
                "comune": None,
                "minx": bounds[0],
                "miny": bounds[1],
                "maxx": bounds[2],
                "maxy": bounds[3],
                "issue": "Layer bounding box is outside expected Lombardia UTM33 range",
                "severity": "BLOCKER",
            }
        )

    if not gdf.empty:
        hashes = gdf.geometry.apply(_geometry_hash)
        duplicate_mask = hashes.duplicated(keep=False) & hashes.notna()
        if duplicate_mask.any():
            duplicate_frame = gdf.loc[duplicate_mask].copy()
            duplicate_frame["__geometry_hash"] = hashes.loc[duplicate_mask]
            for idx, row in duplicate_frame.iterrows():
                duplicate_rows.append(
                    {
                        "dataset": dataset_name,
                        "kind": dataset_kind,
                        "layer": layer_name,
                        "feature_id": row.get(oid_field, idx) if oid_field else idx,
                        "comune": row.get(comune_field) if comune_field else None,
                        "geometry_hash": row["__geometry_hash"],
                        "issue": "Exact duplicate geometry candidate",
                        "severity": "WARNING",
                    }
                )

    for field in ["URL", "url"]:
        if field in gdf.columns:
            nullish = gdf[field].isna() | (gdf[field].astype(str).str.strip() == "")
            for idx, row in gdf.loc[nullish].iterrows():
                attribute_rows.append(
                    {
                        "dataset": dataset_name,
                        "kind": dataset_kind,
                        "layer": layer_name,
                        "feature_id": row.get(oid_field, idx) if oid_field else idx,
                        "field": field,
                        "value": row.get(field),
                        "issue": "Missing URL",
                        "severity": "WARNING",
                    }
                )

    for field in ["DESCR", "Descr", "descr"]:
        if field in gdf.columns:
            too_long = gdf[field].fillna("").astype(str).str.len() > 80
            for idx, row in gdf.loc[too_long].iterrows():
                attribute_rows.append(
                    {
                        "dataset": dataset_name,
                        "kind": dataset_kind,
                        "layer": layer_name,
                        "feature_id": row.get(oid_field, idx) if oid_field else idx,
                        "field": field,
                        "value": row.get(field),
                        "issue": "DESCR longer than 80 characters",
                        "severity": "WARNING",
                    }
                )

    return inventory_rows, field_rows, geometry_rows, coord_rows, duplicate_rows, attribute_rows


def scan_geoportale(config_path: Path, output_override: Path | None = None) -> ScanResult:
    """Scan configured local MS/CLE datasets and write first-level CSV reports."""

    cfg = load_config(config_path)
    out_dir = output_override or cfg.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    inventory_rows: list[dict] = []
    field_rows: list[dict] = []
    geometry_rows: list[dict] = []
    coord_rows: list[dict] = []
    duplicate_rows: list[dict] = []
    attribute_rows: list[dict] = []
    runtime_rows: list[dict] = []

    for dataset in cfg.datasets:
        if not dataset.path.exists():
            runtime_rows.append(
                {
                    "dataset": dataset.name,
                    "kind": dataset.kind,
                    "path": str(dataset.path),
                    "issue": "Dataset path does not exist",
                    "severity": "BLOCKER",
                }
            )
            continue

        try:
            layers = pyogrio.list_layers(dataset.path)
        except Exception as exc:
            runtime_rows.append(
                {
                    "dataset": dataset.name,
                    "kind": dataset.kind,
                    "path": str(dataset.path),
                    "issue": f"Cannot list layers: {exc}",
                    "severity": "BLOCKER",
                }
            )
            continue

        for layer_info in layers:
            layer_name = str(layer_info[0])
            try:
                rows = _scan_layer(cfg, dataset.name, dataset.kind, dataset.path, layer_name)
            except Exception as exc:
                runtime_rows.append(
                    {
                        "dataset": dataset.name,
                        "kind": dataset.kind,
                        "path": str(dataset.path),
                        "layer": layer_name,
                        "issue": f"Cannot scan layer: {exc}",
                        "severity": "BLOCKER",
                    }
                )
                continue
            inv, fields, geom, coords, dupes, attrs = rows
            inventory_rows.extend(inv)
            field_rows.extend(fields)
            geometry_rows.extend(geom)
            coord_rows.extend(coords)
            duplicate_rows.extend(dupes)
            attribute_rows.extend(attrs)

    _write_csv(out_dir / "01_inventory_layers.csv", inventory_rows)
    _write_csv(out_dir / "02_inventory_fields.csv", field_rows)
    _write_csv(out_dir / "03_geometry_invalid.csv", geometry_rows)
    _write_csv(out_dir / "04_coordinate_anomalies.csv", coord_rows)
    _write_csv(out_dir / "05_duplicate_geometries.csv", duplicate_rows)
    _write_csv(out_dir / "06_attribute_warnings.csv", attribute_rows)
    _write_csv(out_dir / "99_runtime_messages.csv", runtime_rows)

    summary_rows = [
        {"report": "01_inventory_layers.csv", "rows": len(inventory_rows)},
        {"report": "02_inventory_fields.csv", "rows": len(field_rows)},
        {"report": "03_geometry_invalid.csv", "rows": len(geometry_rows)},
        {"report": "04_coordinate_anomalies.csv", "rows": len(coord_rows)},
        {"report": "05_duplicate_geometries.csv", "rows": len(duplicate_rows)},
        {"report": "06_attribute_warnings.csv", "rows": len(attribute_rows)},
        {"report": "99_runtime_messages.csv", "rows": len(runtime_rows)},
    ]
    _write_csv(out_dir / "00_summary.csv", summary_rows)

    # Optional Excel summary when openpyxl is installed.
    try:
        with pd.ExcelWriter(out_dir / "riepilogo_scan_geoportale.xlsx") as writer:
            pd.DataFrame(summary_rows).to_excel(writer, index=False, sheet_name="summary")
            pd.DataFrame(inventory_rows).to_excel(writer, index=False, sheet_name="layers")
            pd.DataFrame(geometry_rows).to_excel(writer, index=False, sheet_name="invalid_geom")
            pd.DataFrame(coord_rows).to_excel(writer, index=False, sheet_name="coord_anom")
            pd.DataFrame(duplicate_rows).to_excel(writer, index=False, sheet_name="duplicates")
            pd.DataFrame(attribute_rows).to_excel(writer, index=False, sheet_name="attributes")
    except Exception:
        pass

    warning_count = len(geometry_rows) + len(coord_rows) + len(duplicate_rows) + len(attribute_rows) + len(runtime_rows)
    return ScanResult(output_dir=out_dir, layer_count=len(inventory_rows), warning_count=warning_count)
