import json
from pathlib import Path

from huxleyi_ms_cle.cli import main


def test_normalize_creates_workspace_and_manifest(tmp_path: Path) -> None:
    incoming = tmp_path / "incoming_pkg"
    incoming.mkdir(parents=True, exist_ok=True)
    (incoming / "raw.txt").write_text("raw", encoding="utf-8")

    out_workspace = tmp_path / "workspace"
    exit_code = main(["normalize", str(incoming), "--out", str(out_workspace)])

    assert exit_code == 0
    assert out_workspace.exists()
    manifest_path = out_workspace / "workspace_manifest.json"
    assert manifest_path.exists()
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert payload["kind"] == "incoming"
    assert "created_dirs" in payload
