#!/usr/bin/env python3
"""
Analizza lo storico raccolto in data/presenze.csv e ne ricava i profili
di occupazione del Pronto Soccorso: media per ora del giorno, media per
giorno della settimana, e i picchi.

Uso:
    python analizza.py                      # usa data/presenze.csv
    python analizza.py altro_file.csv       # usa un file diverso

Produce:
    - a schermo: tabella oraria, picchi, media per giorno della settimana
    - analisi/curva_oraria.png   (se matplotlib e' installato)
    - analisi/profilo_settimana.png

Le tabelle usano solo la libreria standard. Il grafico richiede matplotlib
(pip install matplotlib); se manca, lo script fa comunque le tabelle e
segnala come installarlo.
"""

from __future__ import annotations

import csv
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean

GIORNI = ["Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom"]


def carica(path: Path) -> list[dict]:
    if not path.exists():
        sys.exit(f"File non trovato: {path}. Fai girare prima lo scraper.")
    righe = []
    with path.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r.get("codice") != "totali":
                continue  # per l'occupazione complessiva basta la riga 'totali'
            try:
                dt = datetime.fromisoformat(r["ts_scrape"])
                att = int(r["in_attesa"]) if r["in_attesa"] not in ("", None) else 0
                trt = int(r["in_trattamento"]) if r["in_trattamento"] not in ("", None) else 0
            except (ValueError, KeyError):
                continue
            righe.append({"dt": dt, "attesa": att, "trattamento": trt,
                          "presenti": att + trt})
    if not righe:
        sys.exit("Nessuna rilevazione valida (riga codice='totali') nel file.")
    return righe


def media_per(righe, chiave):
    acc = defaultdict(lambda: {"attesa": [], "trattamento": [], "presenti": []})
    for r in righe:
        k = chiave(r["dt"])
        for m in ("attesa", "trattamento", "presenti"):
            acc[k][m].append(r[m])
    return {k: {m: mean(v[m]) for m in v} for k, v in acc.items()}


def stampa_tabella_oraria(oraria):
    print("\n== Occupazione media per ora del giorno ==")
    print(f"{'ora':>4} | {'in attesa':>10} | {'in cura':>8} | {'presenti':>9} | n.ril.")
    print("-" * 52)
    for h in range(24):
        d = oraria.get(h)
        if not d:
            continue
        print(f"{h:>3}h | {d['attesa']:>10.1f} | {d['trattamento']:>8.1f} | "
              f"{d['presenti']:>9.1f} | {d['n']}")


def main() -> int:
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent / "data" / "presenze.csv"
    righe = carica(path)

    span_ore = (max(r["dt"] for r in righe) - min(r["dt"] for r in righe)).total_seconds() / 3600
    print(f"Rilevazioni: {len(righe)}  |  arco temporale: {span_ore:.1f} ore "
          f"(~{span_ore/24:.1f} giorni)")
    if span_ore < 24:
        print("Nota: meno di 24 ore di dati — i profili sono ancora indicativi.")

    # profili
    per_ora = media_per(righe, lambda dt: dt.hour)
    per_dow = media_per(righe, lambda dt: dt.weekday())
    # conteggio rilevazioni per ora
    cnt = defaultdict(int)
    for r in righe:
        cnt[r["dt"].hour] += 1
    for h in per_ora:
        per_ora[h]["n"] = cnt[h]

    stampa_tabella_oraria(per_ora)

    # picchi
    ora_picco_att = max(per_ora, key=lambda h: per_ora[h]["attesa"])
    ora_picco_pres = max(per_ora, key=lambda h: per_ora[h]["presenti"])
    print("\n== Picchi ==")
    print(f"Ora con piu' pazienti in attesa:   {ora_picco_att:>2}h "
          f"(media {per_ora[ora_picco_att]['attesa']:.1f})")
    print(f"Ora con piu' pazienti presenti:    {ora_picco_pres:>2}h "
          f"(media {per_ora[ora_picco_pres]['presenti']:.1f})")

    print("\n== Media per giorno della settimana ==")
    print(f"{'giorno':>6} | {'in attesa':>10} | {'presenti':>9}")
    print("-" * 34)
    for d in range(7):
        if d in per_dow:
            print(f"{GIORNI[d]:>6} | {per_dow[d]['attesa']:>10.1f} | {per_dow[d]['presenti']:>9.1f}")

    # grafici (opzionali)
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("\n(Per i grafici: pip install matplotlib, poi rilancia.)")
        return 0

    outdir = Path(__file__).parent / "analisi"
    outdir.mkdir(exist_ok=True)

    ore = sorted(per_ora)
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(ore, [per_ora[h]["attesa"] for h in ore], "-o", label="in attesa", color="#c0392b")
    ax.plot(ore, [per_ora[h]["trattamento"] for h in ore], "-o", label="in trattamento", color="#2c3e50")
    ax.plot(ore, [per_ora[h]["presenti"] for h in ore], "--", label="presenti (totale)", color="#7f8c8d")
    ax.set_xlabel("ora del giorno")
    ax.set_ylabel("pazienti (media)")
    ax.set_title("PS Santo Stefano — occupazione media per ora")
    ax.set_xticks(range(0, 24, 2))
    ax.grid(alpha=.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(outdir / "curva_oraria.png", dpi=130)

    dows = sorted(per_dow)
    fig2, ax2 = plt.subplots(figsize=(8, 4.5))
    ax2.bar([GIORNI[d] for d in dows], [per_dow[d]["presenti"] for d in dows], color="#c0392b")
    ax2.set_ylabel("presenti (media)")
    ax2.set_title("PS Santo Stefano — presenti medi per giorno della settimana")
    ax2.grid(axis="y", alpha=.3)
    fig2.tight_layout()
    fig2.savefig(outdir / "profilo_settimana.png", dpi=130)

    print(f"\nGrafici salvati in: {outdir}/curva_oraria.png e profilo_settimana.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
