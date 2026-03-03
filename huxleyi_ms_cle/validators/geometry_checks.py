from __future__ import annotations

from dataclasses import dataclass


@dataclass
class GeometryCheckResult:
    invalid_count: int


def count_invalid_geometries(gdf) -> GeometryCheckResult:
    if gdf.empty:
        return GeometryCheckResult(invalid_count=0)
    invalid_count = int((~gdf.geometry.is_valid).sum())
    return GeometryCheckResult(invalid_count=invalid_count)
