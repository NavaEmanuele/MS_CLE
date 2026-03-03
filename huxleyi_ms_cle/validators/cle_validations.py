from __future__ import annotations

from pathlib import Path

from huxleyi_ms_cle.reports import UnifiedReport
from huxleyi_ms_cle.validators.ms_validations import validate_workspace


def validate_cle_workspace(workspace: Path, report: UnifiedReport) -> None:
    """Current CLE validation reuses generic vector checks."""
    validate_workspace(workspace, report)
