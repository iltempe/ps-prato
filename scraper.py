#!/usr/bin/env python3
"""
Raccoglie le presenze in tempo reale nei Pronto Soccorso via l'API pubblica
di prontosoccorso.live, e ne costruisce uno storico (la fonte espone solo
l'istantanea corrente, nessun archivio).

Fonte:  https://api.prontosoccorso.live/api/<regione>/<provincia>
Esempio: https://api.prontosoccorso.live/api/toscana/prato
         -> "Nuovo Ospedale S. Stefano di Prato", presenze per codice colore
            (rosso/giallo/verde/azzurro/bianco), divise tra pazienti in attesa
            e in trattamento.

Nota: prontosoccorso.live e' un aggregatore di terze parti. Per Prato e'
oggi l'unica via pubblica comoda, dato che il portale USL non espone piu' il
Santo Stefano. La fonte primaria resta l'Azienda USL Toscana Centro.

Output: data/presenze.csv (una riga per ogni ospedale x codice, a ogni campionamento)
    ts_scrape        -> istante del campionamento (ora locale Europe/Rome, ISO 8601)
    regione, provincia
    ospedale
    codice           -> rosso|giallo|verde|azzurro|bianco|totali
    in_attesa        -> pazienti in attesa
    in_trattamento   -> pazienti in trattamento
"""

from __future__ import annotations

import csv
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

# Aggiungi qui altre coppie (regione, provincia) se vuoi allargare la raccolta.
TARGETS = [("toscana", "prato")]

API = "https://api.prontosoccorso.live/api/{regione}/{provincia}"
OUT = Path(__file__).parent / "data" / "presenze.csv"
TZ = ZoneInfo("Europe/Rome")
FIELDS = ["ts_scrape", "regione", "provincia", "ospedale",
          "codice", "in_attesa", "in_trattamento"]
CODICI = ["rosso", "giallo", "verde", "azzurro", "bianco", "totali"]


def fetch(regione: str, provincia: str) -> dict:
    url = API.format(regione=regione, provincia=provincia)
    r = requests.get(url, headers={
        "User-Agent": "prato-civic-data-collector (+github actions)",
        "Accept": "application/json",
    }, timeout=30)
    r.raise_for_status()
    return r.json()


def rows_from(payload: dict, regione: str, provincia: str, ts: str) -> list[dict]:
    if not payload.get("status"):
        raise ValueError(f"risposta non valida per {regione}/{provincia}")
    out: list[dict] = []
    for osp in payload.get("data", []):
        nome = osp.get("nome") or osp.get("descrizione") or osp.get("key")
        d = (osp.get("data") or {}).get("data") or {}
        for cod in CODICI:
            c = d.get(cod)
            if not isinstance(c, dict):
                continue
            extra = c.get("extra") or {}
            att = (extra.get("in_attesa") or {}).get("value")
            trt = (extra.get("in_trattamento") or {}).get("value")
            out.append({
                "ts_scrape": ts, "regione": regione, "provincia": provincia,
                "ospedale": nome, "codice": cod,
                "in_attesa": att, "in_trattamento": trt,
            })
    if not out:
        raise ValueError(f"nessun dato estratto per {regione}/{provincia}")
    return out


def append(rows: list[dict]) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    new_file = not OUT.exists()
    with OUT.open("a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if new_file:
            w.writeheader()
        w.writerows(rows)


def main() -> int:
    ts = datetime.now(TZ).isoformat(timespec="seconds")
    all_rows: list[dict] = []
    for regione, provincia in TARGETS:
        try:
            all_rows += rows_from(fetch(regione, provincia), regione, provincia, ts)
        except Exception as e:  # una provincia non deve far fallire le altre
            print(f"[{ts}] ERRORE {regione}/{provincia}: {e}", file=sys.stderr)
    if not all_rows:
        print(f"[{ts}] nessun dato raccolto")
        return 1
    append(all_rows)
    osp = len({r["ospedale"] for r in all_rows})
    print(f"[{ts}] +{len(all_rows)} righe da {osp} ospedali")
    return 0


if __name__ == "__main__":
    sys.exit(main())
