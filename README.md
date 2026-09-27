# PS Prato Live — raccolta storica delle presenze nei PS toscani (fonte prontosoccorso.live)

Costruisce uno **storico** delle presenze in tempo reale nei Pronto Soccorso
della Toscana coperti dall'API pubblica di prontosoccorso.live, campionando ogni
15 minuti tramite una GitHub Action e appendendo a un CSV versionato. Il focus
resta il **Santo Stefano di Prato** (in primo piano sulla dashboard), ma la
raccolta copre ora **tutti i 10 PS** delle province di Firenze, Pistoia, Prato e
Siena, così da poter confrontare l'affollamento tra strutture.

## Fonte

`https://api.prontosoccorso.live/api/toscana/{provincia}` con
`provincia ∈ {firenze, pistoia, prato, siena}`.

Ogni risposta contiene più ospedali, ciascuno con nome, coordinate e le presenze
per codice colore divise tra pazienti **in attesa** e **in trattamento**.

> Nota: prontosoccorso.live è un aggregatore di terze parti. Le **fonti primarie**
> sono l'**Azienda USL Toscana Centro** (Firenze, Pistoia, Prato — 9 ospedali) e
> l'**AOU Senese** (Siena, Policlinico Le Scotte — 1 ospedale). Per un dato
> ufficiale e storico si veda l'accesso civico ai flussi EMUR.

### Ospedali coperti (10)

**USL Toscana Centro (9)**
- Firenze — Ospedale San Giovanni di Dio
- Firenze — Ospedale Santa Maria Nuova
- Bagno a Ripoli — Ospedale Santa Maria Annunziata
- Empoli — Ospedale San Giuseppe
- Borgo San Lorenzo — Nuovo Ospedale del Mugello
- Pistoia — Ospedale San Jacopo
- San Marcello Piteglio — P.I.O.T
- Pescia — Ospedale SS. Cosma e Damiano
- **Prato — Nuovo Ospedale S. Stefano** (struttura in primo piano)

**AOU Senese (1)**
- Siena — Policlinico Santa Maria alle Scotte (Le Scotte)

> Nomenclatura triage: USL Toscana Centro usa rosso/giallo/verde/azzurro/bianco;
> l'AOU Senese usa rosso/**arancione**/azzurro/verde/bianco. I codici vengono
> letti dinamicamente, così il CSV riflette quelli reali di ogni struttura.

Per allargare la raccolta ad altre province, aggiungi coppie `(regione, provincia)`
alla lista `TARGETS` in `scraper.py`.

## Formato dati — `data/presenze.csv`

Una riga per ogni ospedale × codice, a ogni campionamento:

| colonna          | significato                                             |
|------------------|---------------------------------------------------------|
| `ts_scrape`      | istante del campionamento (ora locale Europe/Rome, ISO) |
| `regione`, `provincia` |                                                   |
| `ospedale`       | nome presidio (distingue i PS nello stesso file)        |
| `codice`         | rosso, giallo/arancione, verde, azzurro, bianco, totali |
| `in_attesa`      | pazienti in attesa                                      |
| `in_trattamento` | pazienti in trattamento                                 |
| `lat`, `lng`     | coordinate del presidio (per la mappa)                  |

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
