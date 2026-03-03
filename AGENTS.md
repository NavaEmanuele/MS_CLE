# MS_CLE Agent Guide

## Main Commands
- `python -m huxleyi_ms_cle ingest --zip <zip> --workspace <dir>`
- `python -m huxleyi_ms_cle normalize <path> --out <workspace> [--kind incoming|delivery] [--profile ms|cle|mscle]`
- `python -m huxleyi_ms_cle validate <workspace> --out <outdir> [--kind incoming|delivery] [--profile ms|cle|mscle]`
- `python -m huxleyi_ms_cle scan <workspace> --out <json>`
- `python -m huxleyi_ms_cle build <workspace> --out <outdir> [--kind incoming|delivery] [--profile ms|cle|mscle] [--format shp|gpkg|both] [--zip <zip_path>]`

## Safety Rules
- Never commit files under `data_private/`.
- Never commit files under `output/`.
- Do not modify legacy scripts under `scripts/`.

## Test Commands
- Standard: `python -m pytest -q tests -p no:cacheprovider`
- If temp permission issues appear on Windows, force base temp in `%TEMP%`:
  - `python -m pytest -q tests -p no:cacheprovider --basetemp "%TEMP%\\mscle-pytest"`
