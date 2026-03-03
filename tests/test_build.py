import json
import os
import shutil
import tempfile
from pathlib import Path

import geopandas as gpd
import yaml
from shapely.geometry import Point

from huxleyi_ms_cle.cli import main


def _write_yaml(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _mk_temp_dir() -> Path:
    candidate = next(tempfile._get_candidate_names())
    path = Path.cwd() / f".tmp_test_build_{candidate}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _setup_build_schemas(root: Path, required_dirs: list[str], layers: list[dict], actions: list[dict], dict_payload: dict) -> Path:
    schema_root = root / "schemas_build_test"
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
    _write_yaml(schema_root / "delivery" / "build_actions.yaml", {"version": 1, "actions": actions})
    _write_yaml(schema_root / "dicts" / "indagini.yaml", dict_payload)
    return schema_root


def test_build_set_values_template_url(monkeypatch) -> None:
    tmp_path = _mk_temp_dir()
    try:
        workspace = tmp_path / "workspace"
        src_shp = workspace / "Indagini" / "Ind_pu.shp"
        src_shp.parent.mkdir(parents=True, exist_ok=True)
        gdf = gpd.GeoDataFrame({"ID_SPU": [1001, 1002], "geometry": [Point(10, 45), Point(11, 46)]}, crs="EPSG:32633")
        gdf.to_file(src_shp)

        schema_root = _setup_build_schemas(
            tmp_path,
            required_dirs=["Indagini", "MS1", "MS2", "Plot"],
            layers=[{"name": "Ind_pu", "path": "Indagini/Ind_pu.shp", "required_fields": [], "not_null_fields": [], "unique_fields": []}],
            actions=[
                {
                    "layer": "Indagini/Ind_pu.shp",
                    "add_fields": [{"name": "URL", "type": "str", "length": 254}],
                    "set_values": [{"field": "URL", "expr": "template", "template": "https://example.test/{ID_SPU}.pdf"}],
                }
            ],
            dict_payload={"mappings": {}},
        )
        monkeypatch.setenv("HUXLEYI_SCHEMAS_ROOT", str(schema_root))

        outdir = tmp_path / "delivery_out"
        exit_code = main(["build", str(workspace), "--out", str(outdir), "--kind", "delivery", "--profile", "ms", "--format", "shp"])
        assert exit_code == 0
        out_gdf = gpd.read_file(outdir / "Indagini" / "Ind_pu.shp")
        assert out_gdf.loc[0, "URL"] == "https://example.test/1001.pdf"
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_build_set_values_dict_mapping_descr(monkeypatch) -> None:
    tmp_path = _mk_temp_dir()
    try:
        workspace = tmp_path / "workspace"
        src_shp = workspace / "Indagini" / "Ind_pu.shp"
        src_shp.parent.mkdir(parents=True, exist_ok=True)
        gdf = gpd.GeoDataFrame(
            {"ID_SPU": [1001, 1002], "cod": ["PA", "ALTRO"], "geometry": [Point(10, 45), Point(11, 46)]},
            crs="EPSG:32633",
        )
        gdf.to_file(src_shp)

        schema_root = _setup_build_schemas(
            tmp_path,
            required_dirs=["Indagini", "MS1", "MS2", "Plot"],
            layers=[{"name": "Ind_pu", "path": "Indagini/Ind_pu.shp", "required_fields": [], "not_null_fields": [], "unique_fields": []}],
            actions=[
                {
                    "layer": "Indagini/Ind_pu.shp",
                    "add_fields": [{"name": "DESCR", "type": "str", "length": 254}],
                    "set_values": [{"field": "DESCR", "expr": "dict", "source_field": "cod"}],
                    "dict": "schemas/dicts/indagini.yaml",
                }
            ],
            dict_payload={"mappings": {"PA": "Pozzo per Acqua", "ALTRO": "Altro"}},
        )
        monkeypatch.setenv("HUXLEYI_SCHEMAS_ROOT", str(schema_root))

        outdir = tmp_path / "delivery_out"
        exit_code = main(["build", str(workspace), "--out", str(outdir), "--kind", "delivery", "--profile", "ms", "--format", "shp"])
        assert exit_code == 0
        out_gdf = gpd.read_file(outdir / "Indagini" / "Ind_pu.shp")
        assert out_gdf.loc[0, "DESCR"] == "Pozzo per Acqua"
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_build_truncates_long_field_name_and_registers_mapping(monkeypatch) -> None:
    tmp_path = _mk_temp_dir()
    try:
        workspace = tmp_path / "workspace"
        src_shp = workspace / "Indagini" / "Ind_pu.shp"
        src_shp.parent.mkdir(parents=True, exist_ok=True)
        gdf = gpd.GeoDataFrame({"ID_SPU": [1001], "geometry": [Point(10, 45)]}, crs="EPSG:32633")
        gdf.to_file(src_shp)

        long_name = "DESCRIZIONE_LUNGA_CAMPO"
        schema_root = _setup_build_schemas(
            tmp_path,
            required_dirs=["Indagini"],
            layers=[{"name": "Ind_pu", "path": "Indagini/Ind_pu.shp", "required_fields": [], "not_null_fields": [], "unique_fields": []}],
            actions=[
                {
                    "layer": "Indagini/Ind_pu.shp",
                    "add_fields": [{"name": long_name, "type": "str", "length": 12}],
                    "set_values": [{"field": long_name, "expr": "literal:ABCDE123456789"}],
                }
            ],
            dict_payload={"mappings": {}},
        )
        monkeypatch.setenv("HUXLEYI_SCHEMAS_ROOT", str(schema_root))

        outdir = tmp_path / "delivery_out"
        exit_code = main(["build", str(workspace), "--out", str(outdir), "--kind", "delivery", "--profile", "ms", "--format", "shp"])
        assert exit_code == 0
        out_gdf = gpd.read_file(outdir / "Indagini" / "Ind_pu.shp")
        assert any(col.startswith("DESCRIZION") for col in out_gdf.columns)
        assert len(str(out_gdf.iloc[0][next(col for col in out_gdf.columns if col.startswith("DESCRIZION"))])) <= 12

        build_report = json.loads((outdir / "build_report.json").read_text(encoding="utf-8"))
        layer_info = build_report["layers"][0]
        assert layer_info["field_name_mapping"].get(long_name) is not None
        assert len(layer_info["warnings"]) >= 1
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)


def test_build_preserves_structure(monkeypatch) -> None:
    tmp_path = _mk_temp_dir()
    try:
        workspace = tmp_path / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        schema_root = _setup_build_schemas(
            tmp_path,
            required_dirs=["Indagini", "MS1", "MS2", "Plot"],
            layers=[],
            actions=[],
            dict_payload={"mappings": {}},
        )
        monkeypatch.setenv("HUXLEYI_SCHEMAS_ROOT", str(schema_root))

        outdir = tmp_path / "delivery_out"
        exit_code = main(["build", str(workspace), "--out", str(outdir), "--kind", "delivery", "--profile", "ms", "--format", "shp"])
        assert exit_code == 0
        assert (outdir / "Indagini").exists()
        assert (outdir / "MS1").exists()
        assert (outdir / "MS2").exists()
        assert (outdir / "Plot").exists()

        report = json.loads((outdir / "report.json").read_text(encoding="utf-8"))
        assert report["summary"]["blocker"] == 0
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)
