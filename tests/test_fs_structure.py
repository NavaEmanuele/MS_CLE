from pathlib import Path
import shutil
import uuid

from huxleyi_ms_cle.validators.fs import BLOCKER, validate_fs_structure


def test_missing_required_directory_is_blocker() -> None:
    tmp_path = Path.cwd() / f".tmp_test_fs_structure_{uuid.uuid4().hex[:10]}"
    tmp_path.mkdir(parents=True, exist_ok=True)
    try:
        (tmp_path / "MS1").mkdir()

        findings = validate_fs_structure(
            root_dir=tmp_path,
            required_dirs=["MS1", "CLE"],
            required_file_patterns=[],
        )

        assert any(
            f.severity == BLOCKER and f.check_id == "FS001" and (f.location or "").endswith("CLE")
            for f in findings
        )
    finally:
        shutil.rmtree(tmp_path, ignore_errors=True)
