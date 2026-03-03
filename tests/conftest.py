import shutil
import uuid
from pathlib import Path

import pytest


@pytest.fixture
def tmp_path():
    base_dir = Path(__file__).resolve().parents[1] / "data_private" / ".tmp_pytest"
    base_dir.mkdir(parents=True, exist_ok=True)
    path = base_dir / f"mscle-tests-{uuid.uuid4().hex[:10]}"
    path.mkdir(parents=True, exist_ok=True)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
