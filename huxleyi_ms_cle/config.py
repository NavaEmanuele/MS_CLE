from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field


class CliRunContext(BaseModel):
    command: str
    workspace: Path
    outdir: Path
    source_zip: Path | None = None
    tool_version: str = Field(default="0.1.0")
