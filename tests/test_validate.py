import json
import shutil
import uuid
from pathlib import Path

import geopandas as gpd
import yaml
from shapely.geometry import Point, Polygon

from huxleyi_ms_cle.cli import main


def _new_tmp_dir(prefix: str) -> Path:
    path = Path.cwd() / f".{prefix}_{uuid.uuid4().hex[:10]}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_yaml(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _setup_test_schemas(root: Path, required_dirs: list[str] | None = None, layers: list[dict] | None = None) -> Path:
    schema_root = root / "schemas_test"
    required_dirs = required_dirs or []
    layers = layers or []

    _write_yaml(
        schema_root / "catalog.yaml",
        {
            "kinds": {
                "delivery": {
                    "fs_schema": "delivery/fs_structure.yaml",
                    "layers_schema": "delivery/layers.yaml",
                },
                "incoming": {
                    "fs_schema": "incoming/fs_structure.yaml",
                    "layers_schema": "incoming/layers.yaml",
                    "mappings": "incoming/mappings.yaml",
                },
            }
        },
    )
    _write_yaml(
        schema_root / "delivery" / "fs_structure.yaml",
        {
            "profiles": {
                "ms": {"required_dirs": required_dirs, "required_files_glob": []},
                "cle": {"required_dirs": [], "required_files_glob": []},
                "mscle": {"required_dirs": required_dirs, "required_files_glob": []},
            },
            "warn_on_extra_dirs": False,
            "ignore_dirs_glob": [],
        },
    )
    _write_yaml(schema_root / "delivery" / "layers.yaml", {"version": 1, "layers": layers})
    _write_yaml(schema_root / "incoming" / "fs_structure.yaml", {"profiles": {"ms": {"required_dirs": [], "required_files_glob": []}}})
    _write_yaml(schema_root / "incoming" / "layers.yaml", {"version": 1, "layers": []})
    _write_yaml(schema_root / "incoming" / "mappings.yaml", {"mappings": []})
    return schema_root


def test_validate_writes_reports_even_if_workspace_missing(monkeypatch) -> None:
    tmp_path = _new_tmp_dir("tmp_test_validate_missing")
    try:
        schema_root = _setup_test_schemas(tmp_path)
        monkeypatch.setenv("HUXLEYI_SCHEMAS_ROOT", str(schema_root))
        workspace = tmp_path / "missing_workspace"
        outdir = tmp_path / "out_missing"

        exit_code = main(["validate", str(workspace), "--out", str(outdir), "--kind", "delivery", "--profile", "ms"])

        assert exit_code == 2
        payload = json.loads((outdir / "report.json").read_text(encoding="utf-8"))
        assert payload["summary"]["blocker"] >= 1
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_validate_missing_required_dir_returns_blocker(monkeypatch) -> None:
    tmp_path = _new_tmp_dir("tmp_test_validate_fs")
    try:
        schema_root = _setup_test_schemas(tmp_path, required_dirs=["MS2"])
        monkeypatch.setenv("HUXLEYI_SCHEMAS_ROOT", str(schema_root))
        workspace = tmp_path / "workspace_bad"
        workspace.mkdir(parents=True, exist_ok=True)
        outdir = tmp_path / "out_bad"

        exit_code = main(["validate", str(workspace), "--out", str(outdir), "--kind", "delivery", "--profile", "ms"])

        assert exit_code == 2
        payload = json.loads((outdir / "report.json").read_text(encoding="utf-8"))
        assert payload["summary"]["blocker"] >= 1
        assert any(item["check_id"] == "FS001" for item in payload["findings"])
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_validate_workspace_ok_has_no_blockers(monkeypatch) -> None:
    tmp_path = _new_tmp_dir("tmp_test_validate_ok")
    try:
        schema_root = _setup_test_schemas(tmp_path)
        monkeypatch.setenv("HUXLEYI_SCHEMAS_ROOT", str(schema_root))
        workspace = tmp_path / "workspace_ok"
        workspace.mkdir(parents=True, exist_ok=True)
        outdir = tmp_path / "out_ok"

        exit_code = main(["validate", str(workspace), "--out", str(outdir), "--kind", "delivery", "--profile", "ms"])
        payload = json.loads((outdir / "report.json").read_text(encoding="utf-8"))

        assert exit_code == 0
        assert payload["summary"]["blocker"] == 0
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_validate_duplicate_id_field_warns(monkeypatch) -> None:
    tmp_path = _new_tmp_dir("tmp_test_validate_dup")
    try:
        layer_path = "GeoTec/test_layer.shp"
        schema_root = _setup_test_schemas(
            tmp_path,
            layers=[
                {
                    "name": "test_layer",
                    "path": layer_path,
                    "required_fields": [],
                    "not_null_fields": ["ID_OBJ"],
                    "unique_fields": ["ID_OBJ"],
                }
            ],
        )
        monkeypatch.setenv("HUXLEYI_SCHEMAS_ROOT", str(schema_root))

        workspace = tmp_path / "workspace_dup"
        shp = workspace / layer_path
        shp.parent.mkdir(parents=True, exist_ok=True)
        gdf = gpd.GeoDataFrame(
            {"ID_OBJ": [1, 1], "geometry": [Point(10, 45), Point(11, 46)]},
            crs="EPSG:32633",
        )
        gdf.to_file(shp)
        outdir = tmp_path / "out_dup"

        exit_code = main(["validate", str(workspace), "--out", str(outdir), "--kind", "delivery", "--profile", "ms"])
        payload = json.loads((outdir / "report.json").read_text(encoding="utf-8"))

        assert exit_code == 0
        assert payload["summary"]["warnings"] >= 1
        assert any(item["check_id"] == "SHP030" for item in payload["findings"])
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_validate_invalid_geometry_is_blocker(monkeypatch) -> None:
    tmp_path = _new_tmp_dir("tmp_test_validate_geom")
    try:
        layer_path = "GeoTec/invalid_geom.shp"
        schema_root = _setup_test_schemas(
            tmp_path,
            layers=[{"name": "invalid_geom", "path": layer_path, "required_fields": [], "not_null_fields": [], "unique_fields": []}],
        )
        monkeypatch.setenv("HUXLEYI_SCHEMAS_ROOT", str(schema_root))

        workspace = tmp_path / "workspace_invalid"
        shp = workspace / layer_path
        shp.parent.mkdir(parents=True, exist_ok=True)
        bowtie = Polygon([(0, 0), (1, 1), (1, 0), (0, 1), (0, 0)])
        gdf = gpd.GeoDataFrame({"ID_OBJ": [1], "geometry": [bowtie]}, crs="EPSG:32633")
        gdf.to_file(shp)
        outdir = tmp_path / "out_invalid"

        exit_code = main(["validate", str(workspace), "--out", str(outdir), "--kind", "delivery", "--profile", "ms"])
        payload = json.loads((outdir / "report.json").read_text(encoding="utf-8"))

        assert exit_code == 2
        assert payload["summary"]["blocker"] >= 1
        assert any(item["check_id"] == "GEO010" for item in payload["findings"])
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)
