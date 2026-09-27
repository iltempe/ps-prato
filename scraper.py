#!/usr/bin/env python3
"""
Raccoglie le presenze in tempo reale nei Pronto Soccorso della Toscana via
l'API pubblica di prontosoccorso.live, e ne costruisce uno storico (la fonte
espone solo l'istantanea corrente, nessun archivio).

Fonte:  https://api.prontosoccorso.live/api/<regione>/<provincia>
Copertura attuale: tutte e quattro le province toscane esposte dall'API
(firenze, pistoia, prato, siena), per un totale di 10 ospedali. Ogni risposta
contiene piu' ospedali nel campo data[], ciascuno con nome, coordinate e le
presenze per codice colore (rosso/giallo/verde/azzurro/bianco + totali),
divise tra pazienti in attesa e in trattamento:
    data[i].data.data[<codice>].extra.in_attesa.value
    data[i].data.data[<codice>].extra.in_trattamento.value

Nota: prontosoccorso.live e' un aggregatore di terze parti. Le fonti primarie
sono l'Azienda USL Toscana Centro (Firenze, Pistoia, Prato) e l'AOU Senese
(Siena - Le Scotte).

Output: data/presenze.csv (una riga per ogni ospedale x codice, a ogni campionamento)
    ts_scrape        -> istante del campionamento (ora locale Europe/Rome, ISO 8601)
    regione, provincia
    ospedale         -> distingue i vari PS nello stesso file
    codice           -> rosso|giallo|verde|azzurro|bianco|totali
    in_attesa        -> pazienti in attesa
    in_trattamento   -> pazienti in trattamento
    lat, lng         -> coordinate dell'ospedale (utili per la mappa)
"""

from __future__ import annotations

import csv
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

# Tutte le province toscane esposte dall'API. Per ciascuna si iterano TUTTI gli
# ospedali restituiti in data[]. Aggiungere qui altre coppie (regione, provincia)
# per allargare la raccolta.
TARGETS = [
    ("toscana", "firenze"),
    ("toscana", "pistoia"),
    ("toscana", "prato"),
    ("toscana", "siena"),
]

API = "https://api.prontosoccorso.live/api/{regione}/{provincia}"
OUT = Path(__file__).parent / "data" / "presenze.csv"
TZ = ZoneInfo("Europe/Rome")
FIELDS = ["ts_scrape", "regione", "provincia", "ospedale",
          "codice", "in_attesa", "in_trattamento", "lat", "lng"]
# I codici NON sono fissi: l'USL Toscana Centro usa rosso/giallo/verde/azzurro/
# bianco, l'AOU Senese (Le Scotte) usa rosso/arancione/azzurro/verde/bianco.
# Percio' i codici si leggono dinamicamente da ogni ospedale (piu' 'totali').
_META_KEYS = {"extra"}  # chiavi non-codice dentro data.data da ignorare

# L'API ha una cache: su cache-miss un ospedale (o l'intera provincia) risponde
# con data == [] e manda i dati via websocket. E' transitorio, quindi si riprova
# qualche volta nello stesso run prima di arrendersi.
RETRIES = 5
RETRY_WAIT = 8  # secondi tra un tentativo e l'altro


def fetch(regione: str, provincia: str) -> dict:
    url = API.format(regione=regione, provincia=provincia)
    r = requests.get(url, headers={
        "User-Agent": "toscana-ps-civic-data-collector (+github actions)",
        "Accept": "application/json",
    }, timeout=30)
    r.raise_for_status()
    return r.json()


def _num(v):
    """Coerce a int quando possibile (i valori arrivano a volte come stringa)."""
    try:
        return int(v)
    except (TypeError, ValueError):
        return v


def _att_trt(extra):
    """Ritorna (in_attesa, in_trattamento) tollerando due forme di 'extra':
    - dict (USL):  {"in_attesa": {"value": N}, "in_trattamento": {"value": M}}
    - list (Siena, nodo 'totali'): [{"label": "...attesa...", "value": N},
                                    {"label": "...visita...",  "value": M}, ...]
    """
    if isinstance(extra, dict):
        att = (extra.get("in_attesa") or {}).get("value")
        trt = (extra.get("in_trattamento") or {}).get("value")
        return _num(att), _num(trt)
    if isinstance(extra, list):
        att = trt = None
        for it in extra:
            if not isinstance(it, dict):
                continue
            lab = (it.get("label") or "").lower()
            if "attesa" in lab:
                att = it.get("value")
            elif "visita" in lab or "trattamento" in lab:
                trt = it.get("value")
        return _num(att), _num(trt)
    return None, None


def rows_from(payload: dict, regione: str, provincia: str, ts: str) -> list[dict]:
    """Estrae le righe di TUTTI gli ospedali della provincia.

    I codici colore vengono letti dinamicamente (nomenclature diverse tra USL e
    AOU Senese). Un ospedale in cache-miss (senza il dict dei codici, o con soli
    valori vuoti) viene saltato: non fa fallire gli altri e non scrive righe vuote.
    """
    if not payload.get("status"):
        raise ValueError(f"risposta non valida per {regione}/{provincia}")
    out: list[dict] = []
    for osp in payload.get("data", []):
        if not isinstance(osp, dict):
            continue
        nome = osp.get("nome") or osp.get("descrizione") or osp.get("key")
        coords = osp.get("coords") or {}
        lat = coords.get("lat")
        lng = coords.get("lng")
        inner = osp.get("data")
        if not isinstance(inner, dict):
            continue  # ospedale in cache-miss: 'data' e' [] o assente
        d = inner.get("data")
        if not isinstance(d, dict):
            continue
        for cod, c in d.items():
            if cod in _META_KEYS or not isinstance(c, dict):
                continue
            att, trt = _att_trt(c.get("extra"))
            if att is None and trt is None:
                continue  # nessun valore utile: salta questo codice
            out.append({
                "ts_scrape": ts, "regione": regione, "provincia": provincia,
                "ospedale": nome, "codice": cod,
                "in_attesa": att, "in_trattamento": trt,
                "lat": lat, "lng": lng,
            })
    return out


def append(rows: list[dict]) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    new_file = not OUT.exists()
    with OUT.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            w.writeheader()
        w.writerows(rows)


def raccogli(regione: str, provincia: str, ts: str) -> list[dict]:
    """Righe per una provincia, con retry se l'INTERA provincia e' in cache-miss.

    Se almeno un ospedale ha dati, si restituisce subito quello che c'e' (gli
    ospedali vuoti sono gia' saltati da rows_from): non si insiste per i singoli
    ospedali mancanti in questo giro.
    """
    ultimo_err: object = None
    for tentativo in range(1, RETRIES + 1):
        try:
            rows = rows_from(fetch(regione, provincia), regione, provincia, ts)
            if rows:
                return rows
            ultimo_err = "nessun ospedale con dati (cache-miss)"
        except Exception as e:  # errore di rete o risposta non valida
            ultimo_err = e
        if tentativo < RETRIES:
            print(f"[{ts}] {regione}/{provincia}: tentativo {tentativo} vuoto/errore "
                  f"({ultimo_err}), riprovo tra {RETRY_WAIT}s")
            time.sleep(RETRY_WAIT)
    print(f"[{ts}] {regione}/{provincia}: nessun dato dopo {RETRIES} tentativi "
          f"({ultimo_err}) - provincia saltata", file=sys.stderr)
    return []


def main() -> int:
    ts = datetime.now(TZ).isoformat(timespec="seconds")
    all_rows: list[dict] = []
    for regione, provincia in TARGETS:
        all_rows += raccogli(regione, provincia, ts)
    if not all_rows:
        # Cache-miss su tutte le province: giro saltato, NON e' un errore.
        # Uscita 0 cosi' il workflow resta verde e semplicemente non committa.
        print(f"[{ts}] nessun dato raccolto in questo giro (previsto: cache-miss)")
        return 0
    append(all_rows)
    osp = len({r["ospedale"] for r in all_rows})
    print(f"[{ts}] +{len(all_rows)} righe da {osp} ospedali")
    return 0


if __name__ == "__main__":
    sys.exit(main())
