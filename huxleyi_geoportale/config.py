"""Configuration helpers for the Geoportale validator."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class DatasetConfig:
    """Single dataset configuration."""

    name: str
    path: Path
    kind: str


@dataclass(frozen=True)
class ScanConfig:
    """Runtime configuration for a scan run."""

    data_root: Path
    output_dir: Path
    datasets: tuple[DatasetConfig, ...]
    expected_epsg: int = 32633
    lombardia_minx: float = 450000.0
    lombardia_maxx: float = 750000.0
    lombardia_miny: float = 4980000.0
    lombardia_maxy: float = 5165000.0
    overlap_min_area_m2: float = 0.01


def _as_path(value: str | Path, base: Path | None = None) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute() and base is not None:
        path = base / path
    return path


def load_config(config_path: Path) -> ScanConfig:
    """Load a local YAML configuration file.

    The local config should not be committed if it contains absolute paths.
    Start from ``config/paths.example.yaml`` and save a local copy such as
    ``config/paths.local.yaml``.
    """

    with config_path.open("r", encoding="utf-8") as handle:
        raw: dict[str, Any] = yaml.safe_load(handle) or {}

    data_root = _as_path(raw.get("data_root", "."))
    output_dir = _as_path(raw.get("output_dir", "outputs/geoportale_scan"), data_root)

    dataset_items = raw.get("datasets", [])
    datasets: list[DatasetConfig] = []
    for item in dataset_items:
        datasets.append(
            DatasetConfig(
                name=str(item["name"]),
                path=_as_path(item["path"], data_root),
                kind=str(item.get("kind", item["name"])).upper(),
            )
        )

    bounds = raw.get("lombardia_bounds_utm33", {}) or {}
    return ScanConfig(
        data_root=data_root,
        output_dir=output_dir,
        datasets=tuple(datasets),
        expected_epsg=int(raw.get("expected_epsg", 32633)),
        lombardia_minx=float(bounds.get("minx", 450000.0)),
        lombardia_maxx=float(bounds.get("maxx", 750000.0)),
        lombardia_miny=float(bounds.get("miny", 4980000.0)),
        lombardia_maxy=float(bounds.get("maxy", 5165000.0)),
        overlap_min_area_m2=float(raw.get("overlap_min_area_m2", 0.01)),
    )
