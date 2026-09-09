# CONTEXT — Dataset PS Prato + indagine saturazione pronto soccorso

Handoff per continuare in Claude Code. Account GitHub di destinazione: **iltempe**.

## Obiettivo

Indagine civica/giornalistica (stile @iltempe, Matteo Tempestini) sulla
**saturazione del Pronto Soccorso del Santo Stefano di Prato**. Serve un dataset
reale dell'occupazione del PS che si aggiorni da solo e uno storico su cui poi
costruire un modello a code (SimPy). Spunto: una notte reale in PS, ~10 ore di
permanenza per ~30 minuti di prestazioni effettive.

## Task immediato in Claude Code

1. Prendere il progetto `ps-prato` (è nello zip `ps-prato.zip` già scaricato; se
   non c'è, ricostruirlo dai dettagli qui sotto).
2. `git init` → commit → creare il repo su GitHub **iltempe** e push.
   Con GitHub CLI: `gh repo create ps-prato --private --source=. --push`
   (c'è anche `setup.sh` che fa init+commit+create+push in un colpo).
3. Sul repo: **Settings → Actions → General → Workflow permissions →
   Read and write**. Poi **Actions → scrape-ps → Run workflow** per il primo giro.
4. Da lì la GitHub Action campiona ogni 15 min e committa il CSV: lo storico
   cresce da solo.

## Fonte dati (real-time)

Endpoint JSON pubblico:
`https://api.prontosoccorso.live/api/toscana/prato`

Restituisce il "Nuovo Ospedale S. Stefano di Prato" con le presenze per codice
colore (rosso/giallo/verde/azzurro/bianco + totali), divise tra **in attesa** e
**in trattamento**.

Estrazione dei valori (struttura JSON):
`data[0].data.data[<codice>].extra.in_attesa.value` e
`...extra.in_trattamento.value`, con `<codice>` in
rosso|giallo|verde|azzurro|bianco|totali.

Note:
- prontosoccorso.live è un **aggregatore di terze parti** (backend Laravel di
  roberto-calabrese, repo `prontosoccorso_api`). Nel suo config di Prato la fonte
  è `https://www-old.uslcentro.toscana.it/psstat/pronto-soccorso-pa.php`
  (dominio legacy USL, raggiunto con header Referer/Origin di uslcentro).
- **Fonte primaria da citare** nei contenuti: **Azienda USL Toscana Centro**.
  L'aggregatore è solo il tramite tecnico.
- Il portale USL "nuovo" (`www.uslcentro.toscana.it`) NON espone più Prato; il
  `www-old` è filtrato per IP (503 da runner esteri). Per questo si passa
  dall'API dell'aggregatore.
- L'API ha una cache: su cache-miss può rispondere vuota e mandare i dati via
  websocket. Se un campionamento torna vuoto, si salta quel giro (previsto).

## Struttura del progetto `ps-prato`

- `scraper.py` — GET dell'API, estrae il Santo Stefano, appende a
  `data/presenze.csv`. Dipendenza: solo `requests`. `TARGETS = [("toscana","prato")]`
  (estendibile ad altre province).
- `.github/workflows/scrape.yml` — cron `*/15 * * * *` + `workflow_dispatch`;
  esegue lo scraper e committa `data/` se cambiato. Richiede permessi
  contents: write (vedi passo 3).
- `analizza.py` — legge lo storico e produce tabella oraria, picchi, media per
  giorno della settimana; salva due grafici in `analisi/` (richiede matplotlib,
  `requirements-analisi.txt`).
- `requirements.txt` (requests) / `requirements-analisi.txt` (matplotlib)
- `setup.sh` — init+commit+`gh repo create`+push in un comando.
- `README.md`, `LICENSE` (MIT), `.gitignore`, `data/.gitkeep`.

Formato `data/presenze.csv` (una riga per ospedale × codice, a ogni giro):
`ts_scrape, regione, provincia, ospedale, codice, in_attesa, in_trattamento`
(`ts_scrape` = ora locale Europe/Rome, ISO 8601). Nessun dedup: il campionamento
temporale è l'obiettivo.

Avvertenze GitHub Actions: il cron è best-effort (ritardi/salti possibili);
dopo 60 giorni senza commit i workflow schedulati vengono sospesi (non è un
problema finché lo scraper committa).

## Cosa è già stato fatto (non ripetere)

- **Serie storica accessi per RESIDENZA** (ARS Toscana, indicatore 1657),
  comune di Prato + zona Pratese, 2010–2025, estratta in CSV
  (`accessi_ps_prato_ARS_2010-2025.csv`). NB: è per residenza/tasso, diversa
  dagli accessi ALLA struttura (Santo Stefano ~85.714 nel 2022).
- **Accesso civico** inviato ad AUSL Toscana Centro (PEC
  `urp.uslcentro@postacert.toscana.it`) per i dati EMUR PER STRUTTURA del
  Santo Stefano: accessi per codice triage, permanenza media, quota >8h e >24h,
  boarding (attesa posto letto), tasso di abbandono, dotazione/organico.
  Termine 30 giorni; poi eventuale riesame al RPCT.
- Verificato che PNE/AGENAS espone gli indicatori PS solo a livello
  TERRITORIALE (ASL/residenza), non per singola struttura → il dato di struttura
  arriva solo dall'accesso civico.

## Prossimo passo dopo il dataset

Modello del PS come **coda a priorità multi-server** (SimPy), con due colli di
bottiglia da rendere leve parametriche:
1. **Medico che dimette** = risorsa condivisa; la dimissione ha priorità più
   bassa e viene scavalcata dai codici gravi → spiega l'attesa lunga per uscire.
2. **Attrezzature** (ecografo, laboratorio) = risorse a capacità fissa.
Metriche obiettivo: permanenza per codice, boarding, abbandoni, indice di
sovraffollamento. L'occupazione istantanea (da questo dataset) alimenta gli
arrivi/coda; permanenza e boarding arrivano dai dati EMUR dell'accesso civico.
