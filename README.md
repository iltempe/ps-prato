# PS Prato — raccolta storica delle presenze (fonte prontosoccorso.live)

Costruisce uno **storico** delle presenze in tempo reale nel Pronto Soccorso
del Santo Stefano di Prato, campionando ogni 15 minuti l'API pubblica di
prontosoccorso.live tramite una GitHub Action e appendendo a un CSV versionato.

## Fonte

`https://api.prontosoccorso.live/api/toscana/prato`

Restituisce, in JSON, il "Nuovo Ospedale S. Stefano di Prato" con le presenze
per codice colore (rosso, giallo, verde, azzurro, bianco) divise tra pazienti
**in attesa** e **in trattamento**.

> Nota: prontosoccorso.live è un aggregatore di terze parti. È oggi l'unica via
> pubblica comoda per Prato, dato che il portale USL Toscana Centro non espone
> più il Santo Stefano. La fonte primaria resta l'Azienda USL Toscana Centro
> (per un dato ufficiale e storico si veda l'accesso civico ai flussi EMUR).

Per allargare la raccolta ad altre province, aggiungi coppie `(regione, provincia)`
alla lista `TARGETS` in `scraper.py`.

## Formato dati — `data/presenze.csv`

Una riga per ogni ospedale × codice, a ogni campionamento:

| colonna          | significato                                             |
|------------------|---------------------------------------------------------|
| `ts_scrape`      | istante del campionamento (ora locale Europe/Rome, ISO) |
| `regione`, `provincia` |                                                   |
| `ospedale`       | nome presidio                                           |
| `codice`         | rosso, giallo, verde, azzurro, bianco, totali           |
| `in_attesa`      | pazienti in attesa                                      |
| `in_trattamento` | pazienti in trattamento                                 |

Ogni campionamento viene sempre appeso (nessun dedup): la serie temporale è
proprio l'obiettivo, e due rilevazioni con gli stessi numeri sono dati validi.

## Setup

1. Crea un repo su GitHub e carica questi file.
2. **Settings → Actions → General → Workflow permissions → Read and write**.
3. La Action gira ogni 15 minuti; avvio manuale da **Actions → scrape-ps → Run workflow**.

## Uso locale

```bash
pip install -r requirements.txt
python scraper.py        # scarica e appende a data/presenze.csv
```

## Analisi dello storico

Quando il CSV ha qualche giorno di dati, `analizza.py` ne ricava i profili di
occupazione:

```bash
pip install -r requirements-analisi.txt
python analizza.py
```

Stampa a schermo la tabella dell'occupazione media per ora del giorno, i picchi
(ora con piu' pazienti in attesa e presenti) e la media per giorno della
settimana; salva inoltre due grafici in `analisi/` (curva oraria e profilo
settimanale). Usa la riga `codice='totali'` per l'occupazione complessiva; per
un'analisi per singolo codice colore basta filtrare la colonna `codice`.

## Nota metodologica

Questo dataset misura l'**occupazione istantanea** (persone in attesa e in
trattamento, ora per ora). Ottimo per mostrare picchi e saturazione nel tempo;
non contiene tempi di permanenza né boarding, che vanno chiesti all'USL (EMUR).

Licenza codice: MIT.
