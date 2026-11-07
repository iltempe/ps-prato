"""Esporta per il sito (pspratolive.it/gemello/) tutto ciò che serve alla versione statica.

    .venv/bin/python modello/esporta.py            # dopo ogni calibrazione / ottimizzazione

Scrive in gemello/ui/dati/:
  config.json            parametri, leve, crescita per codice, valori reali di confronto
  scenario_<var>.json    scenari calibrati (letti dal motore JavaScript nel browser)
  storico.json           serie ASL 2020-2025
  validazione_<var>.json confronto simulato/reale della calibrazione
  affidabilita.json      backtest e validazione storica dello scenario di riferimento
  report_*.html          report di ottimizzazione (Su cosa investire)
e in gemello/ui/: guida.html, metodo.html (dalle versioni .md)
e in gemello/output/: libreria_<var>.npz (analoghi per la previsione pubblicata dalla Action)
"""
from __future__ import annotations

import json
import shutil
import sys
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analoghi as AN  # noqa: E402
import dati as D  # noqa: E402
import gemello as G  # noqa: E402
import ottimizza as O  # noqa: E402
import simulazione as S  # noqa: E402
import storico as ST  # noqa: E402
from pagine import pagina_markdown  # noqa: E402

GEM = D.GEMELLO
UI = GEM / "ui"
DATI = UI / "dati"
OUT = GEM / "output"


def scrivi(nome, obj):
    def pulisci(x):
        if isinstance(x, float) and (x != x or x in (float("inf"), float("-inf"))):
            return None
        if isinstance(x, dict):
            return {str(k): pulisci(v) for k, v in x.items()}
        if isinstance(x, (list, tuple)):
            return [pulisci(v) for v in x]
        return x
    (DATI / nome).write_text(json.dumps(pulisci(S._puro(obj)), ensure_ascii=False, separators=(",", ":")))


def variante_rif(cfg):
    return cfg["turni_medici"]["scenario"] + ("_rivprec" if cfg.get("rivalutazione_precedenza") else "")


def main(con_affidabilita=True):
    DATI.mkdir(parents=True, exist_ok=True)
    cfg = S.carica_config()
    asl, pr = D.carica_asl(cfg["anno_asl"]), D.carica_presenze()
    tgt = S.bersagli(asl, pr)
    rif = variante_rif(cfg)
    scen = sorted(p.stem.replace("scenario_", "") for p in OUT.glob("scenario_*.yaml"))

    # scenari calibrati e validazioni
    for v in scen:
        sc = S.carica_scenario(OUT / f"scenario_{v}.yaml")
        scrivi(f"scenario_{v}.json", asdict(sc))
        if (OUT / f"validazione_{v}.json").exists():
            shutil.copy(OUT / f"validazione_{v}.json", DATI / f"validazione_{v}.json")

    # configurazione per l'interfaccia (equivalente di /api/config + valori reali)
    reports = sorted(p.stem for p in OUT.glob("report_*.md"))
    for r in reports:
        md = (OUT / f"{r}.md").read_text(encoding="utf-8")
        (DATI / f"{r}.html").write_text(pagina_markdown(md, r, css="../style.css", indietro="../#investire"), encoding="utf-8")
    scrivi("config.json", dict(
        esportato=datetime.now().astimezone().isoformat(timespec="minutes"),
        config=cfg, leve=O.carica_leve(), fasce=["08-14", "14-20", "20-02", "02-08"],
        scenari_calibrati=scen, scenario_riferimento=rif, metriche=O.METRICHE,
        crescita=O.crescita_annua(asl, cfg), anni_asl=D.anni_disponibili(),
        presenze=dict(inizio=pr.inizio, fine=pr.fine, n=pr.n),
        asl=dict(anno=asl.anno, accessi=asl.accessi, permanenza=asl.permanenza,
                 boarding_n=asl.boarding_n, boarding_ore=asl.boarding_ore),
        reale=dict(permanenza=sum(asl.ore_paziente.values()) / asl.totale,
                   permanenza_codice=asl.permanenza, p8_codice=asl.p8, p24_codice=asl.p24,
                   accessi_codice=asl.accessi, attesa_visita_codice=tgt["attesa_codice"],
                   presenti_codice=tgt["presenti_codice"], presenti_ora=list(pr.tot_ora),
                   in_attesa_ora=list(pr.attesa_ora)),
        report=reports,
    ))
    scrivi("storico.json", dict(serie=ST.serie(), crescita=ST.crescita_per_codice(),
                                crescita_totale=ST.crescita_totale()))

    # pagine Istruzioni e Metodo
    for md, html, tit in (("GUIDA.md", "guida.html", "Istruzioni · Simulatore PS Prato"),
                          ("METODO.md", "metodo.html", "Metodo · Simulatore PS Prato")):
        (UI / html).write_text(pagina_markdown((GEM / md).read_text(encoding="utf-8"), tit), encoding="utf-8")

    # libreria degli analoghi (scenario di riferimento) per la previsione pubblicata dalla Action
    g = cfg["gemello"]["analoghi"]
    sc = S.carica_scenario(OUT / f"scenario_{rif}.yaml")
    with ProcessPoolExecutor(cfg["simulazione"]["processi"]) as pool:
        lib = G.libreria_analoghi(sc, g["giorni"], g["repliche"], pool)
        pm_p, pm_a = AN.profilo_modello(lib)
        arr = {}
        for i, (T, A, R) in enumerate(lib):
            arr[f"T{i}"] = T.astype(np.float32)
            arr[f"A{i}"] = A.astype(np.int16)
            arr[f"R{i}"] = R.astype(np.int16)
        np.savez_compressed(OUT / f"libreria_{rif}.npz", profilo_presenti=pm_p, profilo_attesa=pm_a,
                            n=len(lib), **arr)
        print(f"libreria analoghi: {OUT / f'libreria_{rif}.npz'} ({(OUT / f'libreria_{rif}.npz').stat().st_size/1e6:.1f} MB)")

        if con_affidabilita:
            print("backtest e validazione storica…")
            b = G.backtest(sc, giorni=cfg["gemello"]["backtest"]["giorni"], ogni_ore=cfg["gemello"]["backtest"]["ogni_ore"],
                           orizzonte=cfg["gemello"]["orizzonte_ore"], pool=pool, opz_analoghi=dict(g))
            s2 = S.carica_scenario(OUT / f"scenario_{rif}.yaml")
            s2.giorni = cfg["gemello"]["regime"]["giorni"]
            storica = ST.validazione_storica(s2, valuta=lambda lst: O.valuta(lst, pool, cfg["gemello"]["regime"]["repliche"]))
            scrivi("affidabilita.json", dict(scenario=rif, backtest=b, storica=storica,
                                             calcolato=datetime.now().astimezone().isoformat(timespec="minutes")))
    print("esportazione completata in", DATI)


if __name__ == "__main__":
    main(con_affidabilita="--senza-affidabilita" not in sys.argv)
