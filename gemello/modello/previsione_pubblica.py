"""Previsione delle prossime ore pubblicata su pspratolive.it (GitHub Action, ogni 15 minuti).

Dipende solo da numpy. Legge data/latest.json (appena scritto dallo scraper), le ultime ore di
data/presenze.csv e la libreria di analoghi dello scenario calibrato (gemello/output/libreria_*.npz),
e scrive gemello/ui/dati/previsione.json.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

QUI = Path(__file__).resolve().parent
sys.path.insert(0, str(QUI))
import analoghi as AN  # noqa: E402

GEM = QUI.parent
REPO = GEM.parent
OSPEDALE = "Prato - Nuovo Ospedale S. Stefano"
COLORI = {"rosso": 1, "giallo": 2, "verde": 3, "azzurro": 4, "bianco": 5}


def config_minima():
    """Legge da config.yaml solo ciò che serve, senza PyYAML (riga per riga)."""
    v = {"turni": "A", "prec": False, "k": 60, "tau": 24, "finestra_ore": 1.0, "allarga": 1.8, "orizzonte": 12}
    for r in (GEM / "config.yaml").read_text(encoding="utf-8").splitlines():
        s = r.split("#")[0].strip()
        for chiave, nome, tipo in (("scenario:", "turni", str), ("rivalutazione_precedenza:", "prec", str),
                                   ("k:", "k", int), ("tau:", "tau", float), ("finestra_ore:", "finestra_ore", float),
                                   ("allarga:", "allarga", float), ("orizzonte_ore:", "orizzonte", float)):
            if s.startswith(chiave) and s.split(":", 1)[1].strip():
                val = s.split(":", 1)[1].strip()
                v[nome] = (val.lower() == "true") if nome == "prec" else tipo(val)
    return v


def serie_osservata():
    serie = defaultdict(lambda: {"attesa": {}, "tratt": {}})
    with open(REPO / "data" / "presenze.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["ospedale"] == OSPEDALE and r["codice"] in COLORI:
                c = COLORI[r["codice"]]
                serie[r["ts_scrape"]]["attesa"][c] = int(r["in_attesa"])
                serie[r["ts_scrape"]]["tratt"][c] = int(r["in_trattamento"])
    return dict(sorted((k, v) for k, v in serie.items() if len(v["attesa"]) == 5))


def main():
    c = config_minima()
    var = c["turni"] + ("_rivprec" if c["prec"] else "")
    z = np.load(GEM / "output" / f"libreria_{var}.npz")
    lib = [(z[f"T{i}"].astype(float), z[f"A{i}"], z[f"R{i}"]) for i in range(int(z["n"]))]
    serie = serie_osservata()
    # stato: latest.json se c'è il Santo Stefano, altrimenti l'ultima riga del CSV
    stato = None
    try:
        j = json.loads((REPO / "data" / "latest.json").read_text())
        for o in j["ospedali"]:
            if o["ospedale"] == OSPEDALE:
                stato = dict(ts=o["ts"], attesa={COLORI[k]: int(v["att"]) for k, v in o["codici"].items() if k in COLORI},
                             tratt={COLORI[k]: int(v["trt"]) for k, v in o["codici"].items() if k in COLORI})
    except Exception:
        pass
    if stato is None:
        ts = list(serie)[-1]
        stato = dict(ts=ts, **serie[ts])
    t0 = datetime.fromisoformat(stato["ts"])
    corr = (AN.profilo_reale(serie), (z["profilo_presenti"], z["profilo_attesa"]))
    p = AN.prevedi_analoghi(lib, stato, t0.hour + t0.minute / 60, c["orizzonte"], k=c["k"], tau=c["tau"],
                            finestra_ore=c["finestra_ore"], allarga=c["allarga"], correzione=corr)
    storia = [(ts, v) for ts, v in serie.items() if datetime.fromisoformat(ts) >= t0 - timedelta(hours=24)]
    r1 = lambda x: [round(float(v), 1) for v in x]  # noqa: E731
    out = dict(
        generato=datetime.now().astimezone().isoformat(timespec="seconds"), scenario=var,
        ultimo=dict(ts=stato["ts"], fonte="https://pspratolive.it/data/latest.json",
                    attesa=stato["attesa"], tratt=stato["tratt"]),
        storia=dict(ts=[t for t, _ in storia],
                    presenti=[sum(v["attesa"].values()) + sum(v["tratt"].values()) for _, v in storia],
                    in_attesa=[sum(v["attesa"].values()) for _, v in storia],
                    per_codice={cc: dict(presenti=[v["attesa"][cc] + v["tratt"][cc] for _, v in storia],
                                         in_attesa=[v["attesa"][cc] for _, v in storia]) for cc in AN.CODICI}),
        previsione=dict(
            ore=r1(p["ore"]), inizio=stato["ts"],
            presenti={k: r1(v) for k, v in p["presenti"].items()},
            in_attesa={k: r1(v) for k, v in p["in_attesa"].items()},
            per_codice={cc: {k: r1(v) for k, v in d.items()} for cc, d in p["per_codice"].items()},
            attesa_codice={cc: {k: r1(v) for k, v in d.items()} for cc, d in p["attesa_codice"].items()},
            prob_oltre={k: [round(float(x), 3) for x in v] for k, v in p["prob_oltre"].items()},
        ),
    )
    dest = GEM / "ui" / "dati" / "previsione.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, separators=(",", ":")))
    print(f"previsione da {stato['ts']}: presenti {sum(stato['attesa'].values()) + sum(stato['tratt'].values())}"
          f" -> +3h {p['presenti']['50'][12]:.0f}")


if __name__ == "__main__":
    main()
