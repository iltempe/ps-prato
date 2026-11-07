# Gemello digitale · PS Santo Stefano di Prato

Copia simulata del Pronto Soccorso, tarata sui dati ASL (accesso civico prot. 158918/2026) e
agganciata alle presenze in tempo reale di pspratolive.it. Locale, non versionato
(escluso con `.git/info/exclude`).

- **[GUIDA.md](GUIDA.md)**: come si usa, per tutti (anche dall'interfaccia: link *Guida*).
- **[METODO.md](METODO.md)**: come è costruito, tarato e verificato (link *Metodo*).

## Avvio

    ./avvia.sh            # aggiorna i dati (git pull), avvia http://localhost:8765, apre il browser

Per vedere sito, dati e gemello insieme in VS Code: apri `../pspratolive.code-workspace`.

## File

| | |
|---|---|
| `config.yaml` | tutti i parametri: obiettivo (-30%), turni medici A/B, rivalutazione, ipotesi, gemello, porta |
| `leve.yaml` | leve d'investimento: cosa cambiano e quanto costano (costi indicativi, da verificare) |
| `app.py` | server locale (solo libreria standard) + API + pagine Guida/Metodo |
| `ui/` | interfaccia: Adesso · Regime annuo · Su cosa investire · Storico ASL · Affidabilità |
| `modello/dati.py` | dati ASL + presenze ogni 15 minuti |
| `modello/storico.py` | serie ASL 2020-2025, crescita per codice, validazione storica |
| `modello/simulazione.py` | simulazione a eventi discreti (SimPy), due percorsi per codice, calibrazione |
| `modello/bilancio.py` | dove sta il tempo: ore-paziente per codice e fase |
| `modello/ottimizza.py` | leve, mix minimo per l'obiettivo (anche per singolo codice), fasce orarie, proiezioni |
| `modello/gemello.py` | previsione dallo stato live (metodo degli analoghi) e backtest |
| `output/` | scenari calibrati, validazioni, report, rilevazioni live raccolte |

Scenario di riferimento: **turni A, rivalutazione con precedenza** (`output/scenario_A_rivprec.yaml`):
è l'unica combinazione che riproduce insieme i tempi ASL per codice e le curve orarie misurate
(vedi METODO §5).
