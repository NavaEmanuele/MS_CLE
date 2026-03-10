# Runbook

## Procedura standard quando si riprende il progetto in VS Code

1. Aprire la root del repository `C:\Users\EMANUELE\MS_CLE`

2. Verificare lo stato Git
   Controllare file modificati, file non tracciati e presenza di cambi locali da non toccare.

3. Rileggere i file guida prima di lavorare
   - `AGENTS.md`
   - `PROJECT_STATUS.md`
   - `NEXT_STEPS.md`
   - `README.md`

4. Rileggere i punti chiave dell'architettura attuale
   - `huxleyi_ms_cle/cli.py`
   - `huxleyi_ms_cle/build.py`
   - `huxleyi_ms_cle/mdb.py`
   - `huxleyi_ms_cle/reporting/`
   - `huxleyi_ms_cle/validators/`

5. Rileggere gli schema centrali
   - `schemas/catalog.yaml`
   - `schemas/incoming/fs_structure.yaml`
   - `schemas/delivery/fs_structure.yaml`
   - eventuali schema coinvolti dal task corrente

6. Identificare il task minimo utile del turno
   Preferire un passo piccolo, verificabile e coerente con `NEXT_STEPS.md`.

7. Prima di modificare codice, capire dove vive davvero la logica
   In questo progetto molte validazioni reali stanno ancora in `cli.py`, non in `validators/`.

8. Se il task tocca il comportamento, eseguire i test rilevanti
   Comando standard:

```powershell
python -m pytest -q tests -p no:cacheprovider
```

   Se su Windows compaiono problemi di temp:

```powershell
python -m pytest -q tests -p no:cacheprovider --basetemp "$env:TEMP\mscle-pytest"
```

9. Non toccare mai queste aree se non richiesto esplicitamente
   - `scripts/`
   - `data_private/`
   - `output/`

10. Dopo le modifiche, ricontrollare
   - file effettivamente cambiati
   - test rilevanti
   - eventuale coerenza con schema e report prodotti

## Regola pratica

Se il repository sembra gia' predisposto per una modularizzazione ma i file sono vuoti, assumere che la logica vera sia ancora nel modulo chiamante e verificarlo prima di intervenire.
