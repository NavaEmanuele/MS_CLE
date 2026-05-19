# Workflow Geoportale MS/CLE

Questo documento descrive la prima impostazione del flusso di lavoro per validare e correggere i geodatabase MS/CLE destinati alla pubblicazione sul Geoportale.

## Obiettivo

Costruire una procedura ripetibile per:

1. conservare intatti i geodatabase originali pubblicati;
2. leggere i GDB MS/CLE da un percorso locale o da disco esterno;
3. generare report leggeri in CSV/XLSX;
4. individuare errori bloccanti, warning e anomalie da verificare manualmente;
5. usare ArcMap/ArcPy solo per le correzioni fisiche sui GDB di lavoro;
6. documentare ogni modifica prima della pubblicazione finale.

## Struttura consigliata del disco esterno

```text
G:/GEO_PORTALE_MS_CLE/
├── 01_GDB_PUBBLICATI_ORIGINALI/
│   ├── microzonazione_sismica_aggiornamento.gdb
│   └── CLE.gdb
├── 02_MATERIALE_COMUNI_ORIGINALE/
├── 03_WORKSPACE_CORREZIONI/
├── 04_OUTPUT_ANALISI/
└── 05_GDB_VALIDATI/
```

Le cartelle `01_GDB_PUBBLICATI_ORIGINALI` e `02_MATERIALE_COMUNI_ORIGINALE` devono essere considerate intoccabili.

## Primo comando disponibile

Il primo modulo aggiunto è uno scanner conservativo: legge i dataset e produce report, senza modificare i dati.

```powershell
python -m huxleyi_geoportale.cli scan --config config/paths.local.yaml
```

Per preparare la configurazione locale:

1. copia `config/paths.example.yaml` in `config/paths.local.yaml`;
2. modifica `data_root`, `output_dir` e i percorsi dei GDB;
3. non caricare `paths.local.yaml` su GitHub.

## Output generati

Lo scanner produce:

| File | Contenuto |
|---|---|
| `00_summary.csv` | riepilogo numero righe per report |
| `01_inventory_layers.csv` | elenco layer, conteggi, CRS e bounding box |
| `02_inventory_fields.csv` | elenco campi, tipi, null e valori unici |
| `03_geometry_invalid.csv` | geometrie non valide |
| `04_coordinate_anomalies.csv` | layer fuori range Lombardia UTM33 |
| `05_duplicate_geometries.csv` | candidati duplicati geometrici esatti |
| `06_attribute_warnings.csv` | URL mancanti, DESCR lunghi, CRS inattesi |
| `99_runtime_messages.csv` | errori di lettura o configurazione |
| `riepilogo_scan_geoportale.xlsx` | riepilogo Excel, se disponibile `openpyxl` |

## Interpretazione delle severità

- `BLOCKER`: problema da risolvere o comprendere prima della pubblicazione;
- `WARNING`: problema da verificare, spesso correggibile in modo semi-automatico;
- `NOTE`: informazione utile, non ancora usata nel primo scanner.

## Prossimi moduli previsti

1. validatore attributivo MS/CLE con regole specifiche per layer;
2. controllo topologico per overlap sopra soglia;
3. report Word automatico;
4. script ArcPy di correzione sicura su copia di lavoro;
5. registro pubblicazione per comune.
