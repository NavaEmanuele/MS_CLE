from __future__ import annotations

import ast
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
OUT = ROOT / "schemas" / "dicts"


def _extract_dict_assignments(py_path: Path) -> dict[str, dict]:
    source = py_path.read_text(encoding="utf-8", errors="ignore")
    tree = ast.parse(source, filename=str(py_path))
    out: dict[str, dict] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
            continue
        name = node.targets[0].id
        if not isinstance(node.value, ast.Dict):
            continue
        try:
            value = ast.literal_eval(node.value)
        except Exception:
            continue
        if isinstance(value, dict) and value:
            if all(isinstance(k, (str, int, float)) for k in value.keys()):
                out[name] = {str(k): str(v) for k, v in value.items()}
    return out


def _write_yaml(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=False), encoding="utf-8")


def main() -> None:
    mapping = {
        "geotec.py": OUT / "geotec.yaml",
        "indagini.py": OUT / "indagini.yaml",
        "cle.py": OUT / "cle.yaml",
    }
    for script_name, out_path in mapping.items():
        script_path = SCRIPTS / script_name
        if not script_path.exists():
            _write_yaml(out_path, {"mappings": {}})
            continue
        extracted = _extract_dict_assignments(script_path)
        merged: dict[str, str] = {}
        for _, dictionary in extracted.items():
            merged.update(dictionary)
        payload = {"mappings": merged, "sources": extracted}
        _write_yaml(out_path, payload)
        print(f"Wrote {out_path} ({len(merged)} entries)")


if __name__ == "__main__":
    main()
