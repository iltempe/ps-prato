# Dati ufficiali — Pronto Soccorso Santo Stefano di Prato

Dati di attività del Pronto Soccorso del Nuovo Ospedale Santo Stefano di Prato,
ottenuti dall'**Azienda USL Toscana Centro** in risposta a un'istanza di
**accesso civico generalizzato** (art. 5, comma 2, D.Lgs. 33/2013).

- **Protocollo risposta:** n. 158918 del 09/09/2026 (riscontro del 06/10/2026)
- **Struttura:** Nuovo Ospedale di Prato Santo Stefano
- **Periodo:** 2019–2025 (il dato 2019 non è recuperabile dal sistema in uso presso l'Azienda)

## File

| File | Contenuto |
|---|---|
| `01_accessi_per_codice_triage.csv` | Accessi annui per codice di triage (1 Emergenza → 5 Non urgenza) |
| `02_tempo_permanenza_per_codice.csv` | Tempo medio di permanenza per codice, per anno |
| `03_accessi_oltre_8h_24h.csv` | N. e % di accessi con permanenza oltre 8h e oltre 24h |
| `04_boarding.csv` | N., % e tempo medio di attesa dei pazienti in boarding (attesa di ricovero) |
| `05_abbandoni.csv` | N. e tasso di accessi che esitano in abbandono |
| `06_risorse.csv` | Postazioni, personale infermieristico, OSS e medico |
| `ORIGINALE_risposta_ASL_accesso_civico.xlsx` | File Excel originale ricevuto dall'Azienda (prova documentale) |

## Note di lettura

- **I tempi sono durate, non orari.** Nei CSV sono espressi in formato durata
  leggibile (es. `23h 39m` = 23 ore e 39 minuti). Nel file Excel originale le
  stesse celle sono formattate come "ora del giorno" (AM/PM), il che è
  fuorviante: `11:39:03 PM` va letto come 23 ore e 39 minuti di permanenza.
  Il tempo di permanenza è calcolato dall'Azienda come `ORA_CHIUSURA − ORA_ACCETTAZIONE`.
- **`ESITO: NOT Inserito per errore`** in fondo ai fogli è un criterio di
  estrazione della query (esclude gli accessi registrati per errore), non un
  difetto dei dati.
- **L'anno 2021** presenta valori anomali (effetto pandemia): va interpretato con cautela.
- Il dato sul numero di ore/giornate in condizione di **sovraffollamento** non è
  stato fornito: l'Azienda dichiara che "si tratta di un dato non supportato dal
  sistema informatico del Pronto Soccorso".

## Licenza e uso

Dati pubblici ottenuti tramite accesso civico generalizzato, riutilizzabili.
Raccolti e pubblicati nell'ambito del progetto civico **pspratolive.it**.
