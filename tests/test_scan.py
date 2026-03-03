import json
import shutil
import uuid
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Point

from huxleyi_ms_cle.cli import main


def test_scan_outputs_layer_metadata() -> None:
    tmp_path = Path.cwd() / f".tmp_test_scan_{uuid.uuid4().hex[:10]}"
    tmp_path.mkdir(parents=True, exist_ok=True)
    try:
        workspace = tmp_path / "workspace"
        workspace.mkdir(parents=True, exist_ok=True)
        shp_path = workspace / "sample.shp"

        gdf = gpd.GeoDataFrame(
            {
                "ID_OBJ": [1, 1, None],
                "NAME": ["a", None, "c"],
                "geometry": [Point(10, 45), Point(11, 46), Point(12, 47)],
            },
            crs="EPSG:4326",
        )
        gdf.to_file(shp_path)

        out_json = tmp_path / "scan.json"
        exit_code = main(["scan", str(workspace), "--out", str(out_json)])

        assert exit_code == 0
        assert out_json.exists()
        payload = json.loads(out_json.read_text(encoding="utf-8"))
        assert payload["version"] == 1
        assert len(payload["layers"]) == 1
        layer = payload["layers"][0]
        assert layer["relpath"] == "sample.shp"
        assert layer["n_records"] == 3
        assert "ID_OBJ" in layer["columns"]
        assert any(key.upper().startswith("ID") for key in layer["duplicate_count"].keys())
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)
