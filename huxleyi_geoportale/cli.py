"""Command line interface for Geoportale MS/CLE validation utilities."""

from __future__ import annotations

import argparse
from pathlib import Path

from .scan import scan_geoportale


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="huxleyi-geoportale",
        description="Scan and validate local MS/CLE Geoportale working datasets.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_parser = subparsers.add_parser(
        "scan",
        help="Create CSV inventories and first-level quality checks from local GDB paths.",
    )
    scan_parser.add_argument(
        "--config",
        required=True,
        help="Path to a local YAML configuration file. Use config/paths.example.yaml as template.",
    )
    scan_parser.add_argument(
        "--out",
        default=None,
        help="Optional output directory override. If omitted, output_dir from config is used.",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "scan":
        result = scan_geoportale(Path(args.config), Path(args.out) if args.out else None)
        print(f"Scan completed. Outputs written to: {result.output_dir}")
        print(f"Layers scanned: {result.layer_count}")
        print(f"Warnings: {result.warning_count}")
        return 0

    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
