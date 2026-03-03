from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import geopandas as gpd


def _parse_fields(raw_fields: list[str]) -> list[str]:
    out: list[str] = []
    for item in raw_fields:
        for token in item.split(","):
            value = token.strip()
            if value and value not in out:
                out.append(value)
    return out


def collect_domain_stats(workspace: Path, fields: list[str]) -> dict[str, Any]:
    stats: list[dict[str, Any]] = []
    for shp_path in sorted(path for path in workspace.rglob("*.shp") if path.is_file()):
        try:
            gdf = gpd.read_file(shp_path)
        except Exception:
            continue
        relpath = str(shp_path.relative_to(workspace)).replace("\\", "/")
        for field in fields:
            if field not in gdf.columns:
                continue
            counts = gdf[field].fillna("<NULL>").astype(str).value_counts(dropna=False)
            stats.append(
                {
                    "layer": relpath,
                    "field": field,
                    "unique_count": int(counts.shape[0]),
                    "frequencies": [{"value": str(value), "count": int(count)} for value, count in counts.items()],
                }
            )
    return {
        "version": 1,
        "workspace": str(workspace),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "stats": stats,
    }


def write_csv(payload: dict[str, Any], csv_path: Path) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["layer", "field", "value", "count"])
        writer.writeheader()
        for item in payload.get("stats", []):
            layer = item.get("layer", "")
            field = item.get("field", "")
            for freq in item.get("frequencies", []):
                writer.writerow(
                    {
                        "layer": layer,
                        "field": field,
                        "value": freq.get("value", ""),
                        "count": freq.get("count", 0),
                    }
                )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export domain value frequencies from shapefiles")
    parser.add_argument("workspace", help="Workspace to scan recursively")
    parser.add_argument("--fields", nargs="+", required=True, help="Field names (supports comma-separated values)")
    parser.add_argument("--out-json", help="Output JSON path")
    parser.add_argument("--out-csv", help="Output CSV path")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    workspace = Path(args.workspace)
    if not workspace.exists() or not workspace.is_dir():
        raise FileNotFoundError(f"Workspace does not exist: {workspace}")

    fields = _parse_fields(args.fields)
    if not fields:
        raise ValueError("No valid fields provided")

    out_json = Path(args.out_json) if args.out_json else None
    out_csv = Path(args.out_csv) if args.out_csv else None
    if out_json is None and out_csv is None:
        raise ValueError("At least one output must be provided: --out-json or --out-csv")

    payload = collect_domain_stats(workspace, fields)

    if out_json is not None:
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    if out_csv is not None:
        write_csv(payload, out_csv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
