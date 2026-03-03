# Audit tecnico completo (MS_CLE)

Data audit: corrente branch `work`.

## Obiettivo
Individuare falle/criticità negli script operativi (`scripts/*.py`) e nel validatore, con priorità a errori che possono produrre output errati o flussi non deterministici.

## Metodo usato
1. Revisione statica dei file Python e dei flussi principali.
2. Compilazione rapida del codice (`compileall`) per intercettare errori di parsing.
3. Verifica CLI (`--help`) per controllare l'accessibilità delle opzioni del validatore.

## Findings

### Critico — entrypoint duplicato e side-effect anticipato in `scripts/indagini.py` (RISOLTO)
- **Problema**: era presente un blocco `if __name__ == '__main__':` in mezzo al file che avviava export/rename prima della definizione delle funzioni successive.
- **Rischio**: esecuzione parziale/non chiara del flusso e comportamento difficile da mantenere.
- **Fix applicato**: introdotta funzione `run_preprocessing()` e orchestrazione unica nel `main()` finale.

### Alto — mapping codici sensibile a typo/concatenazioni implicite in dizionari script (PARZIALMENTE RISOLTO)
- **Problema osservato**: in `scripts/ms1.py` era già stato corretto un caso di stringa isolata che alterava una chiave.
- **Rischio**: descrizioni (`DESCR`) errate e URL non coerenti con i codici ufficiali.
- **Azione consigliata**: mantenere tabelle codici versionate e verificabili (CSV di riferimento), da confrontare automaticamente.

### Medio — placeholder di configurazione non validati (APERTO)
- **Problema**: diversi script dipendono da variabili manuali (`WORKSPACE_BASE`, codici comune, path MDB) senza fail-fast esplicito.
- **Rischio**: run su percorsi vuoti o non corretti con effetti silenziosi.
- **Azione consigliata**: aggiungere validazioni iniziali (`if not WORKSPACE_BASE: raise` / messaggio chiaro e `return` non-zero).

### Medio — dipendenza da `arcpy` senza modalità dry-run (APERTO)
- **Problema**: in ambienti non ArcGIS i controlli completi non sono eseguibili.
- **Rischio**: difficile CI/CD e verifica preventiva su macchine non GIS.
- **Azione consigliata**: introdurre flag `--dry-run` nei workflow principali e check path/campi senza operazioni geoprocessing.

## Correzioni incluse in questa PR
- Refactor entrypoint in `scripts/indagini.py` con funzione `run_preprocessing()`.
- Aggiornamento orchestrazione `main()` per flusso unico, prevedibile e manutenibile.

## Prossimi step consigliati
1. Aggiungere guardrail di configurazione in `scripts/cle.py`, `scripts/geotec.py`, `scripts/ms1.py`, `scripts/indagini.py`.
2. Estrarre i dizionari codici in file dati versionati (CSV/JSON) con validazione automatica.
3. Aggiungere un comando audit unico (es. `scripts/audit.py`) che lanci `compileall`, controlli configurazione minima e reporti esiti.
