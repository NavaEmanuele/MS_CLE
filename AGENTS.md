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

## MDB Relations Configuration
- Edit `schemas/delivery/mdb.yaml` when the real `CLE_db.mdb` structure is confirmed.
- Pozzolengo real patterns:
  - `CLE/CLE_db_*.mdb` (`cle_db`)
  - `Indagini/CdI_Tabelle_*.mdb` (`cdi_db`)
- `tables`: declare only mandatory tables/fields for each DB. Missing declared table/field triggers `MDB030` (`BLOCKER`).
- `relations`: map `CLE/CL_*.shp` IDs to MDB table IDs under `cle_db`.
- If a relation points to a non-declared table, validator emits `MDB040` (`WARN`) with a config hint.
- To require MDB by profile, use per-database `required_for_profiles` (e.g. `["cle", "mscle"]`).
