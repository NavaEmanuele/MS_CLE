from __future__ import annotations

from pathlib import Path

from huxleyi_ms_cle.reports import SEVERITY_BLOCKER, SEVERITY_INFO, SEVERITY_WARN, UnifiedReport
from huxleyi_ms_cle.validators.geometry_checks import count_invalid_geometries


def validate_workspace(workspace: Path, report: UnifiedReport) -> None:
    vector_files = sorted(
        [p for p in workspace.rglob("*") if p.is_file() and p.suffix.lower() in {".shp", ".gpkg", ".geojson", ".json"}]
    )

    if not vector_files:
        report.add(SEVERITY_BLOCKER, "NO_VECTOR_DATA", "No vector files found in workspace.")
        return

    report.add(SEVERITY_INFO, "VECTOR_COUNT", f"Discovered {len(vector_files)} vector file(s).")

    for path in vector_files:
        try:
            import geopandas as gpd

            gdf = gpd.read_file(path, engine="pyogrio")
        except Exception as exc:  # noqa: BLE001
            report.add(SEVERITY_BLOCKER, "READ_ERROR", f"Unable to read dataset: {exc}", file=str(path))
            continue

        if gdf.empty:
            report.add(SEVERITY_WARN, "EMPTY_LAYER", "Layer has no records.", file=str(path))

        if gdf.crs is None:
            report.add(SEVERITY_WARN, "MISSING_CRS", "Layer has no CRS metadata.", file=str(path))

        invalid = count_invalid_geometries(gdf)
        if invalid.invalid_count > 0:
            report.add(
                SEVERITY_WARN,
                "INVALID_GEOMETRY",
                f"Found {invalid.invalid_count} invalid geometry record(s).",
                file=str(path),
            )
