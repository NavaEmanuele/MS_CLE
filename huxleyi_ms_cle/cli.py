from __future__ import annotations

import argparse
import sys
from pathlib import Path

from huxleyi_ms_cle.reporting import Finding, Severity, write_html_report, write_json_report


def _simple_yaml_parse(text: str) -> dict:
    data: dict = {}
    current_list_key: str | None = None
    current_layers: list[dict] | None = None
    current_layer: dict | None = None

    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue

        if line.startswith("layers:"):
            data["layers"] = []
            current_layers = data["layers"]
            current_list_key = None
            current_layer = None
            continue

        if line.startswith("required_dirs:"):
            data["required_dirs"] = []
            current_list_key = "required_dirs"
            current_layers = None
            current_layer = None
            continue

        if line.startswith("required_files:"):
            data["required_files"] = []
            current_list_key = "required_files"
            current_layers = None
            current_layer = None
            continue

        stripped = line.strip()

        if current_list_key and stripped.startswith("- "):
            data[current_list_key].append(stripped[2:].strip())
            continue

        if current_layers is not None and stripped.startswith("- name:"):
            name = stripped.split(":", 1)[1].strip()
            current_layer = {"name": name}
            current_layers.append(current_layer)
            continue

        if current_layer is not None and ":" in stripped:
            key, value = stripped.split(":", 1)
            key = key.strip()
            value = value.strip()
            if value.startswith("[") and value.endswith("]"):
                items = [x.strip() for x in value[1:-1].split(",") if x.strip()]
                current_layer[key] = items
            else:
                current_layer[key] = value

    return data


def _load_yaml(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml

        return yaml.safe_load(text) or {}
    except ModuleNotFoundError:
        return _simple_yaml_parse(text)


def validate_workspace(workspace: Path, schemas_root: Path) -> list[Finding]:
    findings: list[Finding] = []

    fs_schema = _load_yaml(schemas_root / "fs_structure.yaml")
    for rel_dir in fs_schema.get("required_dirs", []):
        target = workspace / rel_dir
        if not target.is_dir():
            findings.append(
                Finding(
                    code="FS_MISSING_DIR",
                    severity=Severity.BLOCKER,
                    message=f"Directory mancante: {rel_dir}",
                    target=rel_dir,
                )
            )

    for rel_file in fs_schema.get("required_files", []):
        target = workspace / rel_file
        if not target.is_file():
            findings.append(
                Finding(
                    code="FS_MISSING_FILE",
                    severity=Severity.BLOCKER,
                    message=f"File mancante: {rel_file}",
                    target=rel_file,
                )
            )

    layers_schema = _load_yaml(schemas_root / "layers_minimal.yaml")
    for layer in layers_schema.get("layers", []):
        name = layer["name"]
        rel_path = layer["path"]
        shp_path = workspace / rel_path

        if not shp_path.exists():
            findings.append(
                Finding(
                    code="LAYER_MISSING",
                    severity=Severity.BLOCKER,
                    message=f"Layer mancante: {name}",
                    target=rel_path,
                )
            )
            continue

        try:
            import geopandas as gpd

            gdf = gpd.read_file(shp_path)
        except Exception as exc:
            findings.append(
                Finding(
                    code="LAYER_READ_ERROR",
                    severity=Severity.BLOCKER,
                    message=f"Errore lettura layer {name}: {exc}",
                    target=rel_path,
                )
            )
            continue

        for field in layer.get("required_fields", []):
            if field not in gdf.columns:
                findings.append(
                    Finding(
                        code="FIELD_MISSING",
                        severity=Severity.BLOCKER,
                        message=f"Campo obbligatorio mancante: {field}",
                        target=f"{rel_path}:{field}",
                    )
                )

        for field in layer.get("not_null_fields", []):
            if field in gdf.columns and gdf[field].isna().any():
                findings.append(
                    Finding(
                        code="FIELD_NULL",
                        severity=Severity.BLOCKER,
                        message=f"Campo {field} contiene valori null.",
                        target=f"{rel_path}:{field}",
                    )
                )

        invalid_count = int((~gdf.geometry.is_valid).sum()) if not gdf.empty else 0
        if invalid_count > 0:
            findings.append(
                Finding(
                    code="GEOMETRY_INVALID",
                    severity=Severity.WARN,
                    message=f"{invalid_count} geometrie non valide in {name}.",
                    target=rel_path,
                    suggestion="Valutare correzione con shapely.make_valid prima del processamento.",
                )
            )

    if not findings:
        findings.append(
            Finding(
                code="VALIDATION_OK",
                severity=Severity.INFO,
                message="Nessuna anomalia rilevata.",
            )
        )

    return findings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="huxleyi_ms_cle")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate", help="Esegue validazioni su workspace")
    validate_parser.add_argument("workspace", type=Path, help="Workspace da validare")
    validate_parser.add_argument("--out", type=Path, required=True, help="Directory output report")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "validate":
        try:
            repo_root = Path(__file__).resolve().parent.parent
            schemas_root = repo_root / "schemas"
            findings = validate_workspace(args.workspace, schemas_root)

            out_dir: Path = args.out
            write_json_report(findings, out_dir / "report.json")
            write_html_report(findings, out_dir / "report.html")

            has_blocker = any(f.severity == Severity.BLOCKER for f in findings)
            return 2 if has_blocker else 0
        except Exception as exc:
            sys.stderr.write(f"Errore runtime: {exc}\n")
            return 1

    return 1
