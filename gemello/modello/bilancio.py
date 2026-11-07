"""Bilancio delle ore-paziente: dove sta il tempo passato in PS.

Legge di Little: ore-paziente/anno = Σ accessi × permanenza media = presenti medi × 8760.
Ridurre la permanenza media del X% significa togliere X% di queste ore.
Scomposizione per fase:
  attesa prima visita  <- presenze "in attesa" misurate (pspratolive.it), riportate al 2025
  boarding             <- dati ASL (n × attesa media), ripartito per codice con quota_ricovero
  processo             <- il resto: visita, esami, consulenze, osservazione, attesa esiti
"""
from __future__ import annotations

import dati as D
from simulazione import carica_config


def bilancio(cfg=None):
    cfg = cfg or carica_config()
    asl, pr = D.carica_asl(cfg["anno_asl"]), D.carica_presenze()
    ore = asl.ore_paziente
    tot = sum(ore.values())
    k = (tot / 8760) / pr.media                  # da presenze autunno 2026 a carico 2025
    qr = cfg["quota_ricovero"]
    peso_b = {c: asl.accessi[c] * qr[c] for c in D.CODICI}
    ore_b_tot = asl.boarding_n * asl.boarding_ore
    righe = {}
    for c in D.CODICI:
        att = pr.attesa_codice[c] * k * 8760
        bo = ore_b_tot * peso_b[c] / sum(peso_b.values())
        righe[c] = dict(totale=ore[c], attesa=att, boarding=bo, processo=ore[c] - att - bo)
    return asl, pr, tot, righe


def testo(target=None):
    cfg = carica_config()
    target = target if target is not None else cfg["target_riduzione"]
    asl, pr, tot, righe = bilancio(cfg)
    fasi = ("attesa", "processo", "boarding")
    L = []
    L.append(f"Ore-paziente {asl.anno}: {tot:,.0f} (= {tot/8760:.0f} presenti in media, "
             f"permanenza media {tot/asl.totale:.1f}h)".replace(",", "."))
    L.append(f"Obiettivo -{target:.0%}: togliere {tot*target:,.0f} ore-paziente/anno "
             f"(permanenza media da {tot/asl.totale:.1f}h a {tot/asl.totale*(1-target):.1f}h)\n".replace(",", "."))
    L.append("| Codice | Accessi | Ore-paziente | Quota | Attesa visita | Processo | Boarding |")
    L.append("|---|---|---|---|---|---|---|")
    for c, r in righe.items():
        L.append(f"| {c} {D.NOMI[c]} | {asl.accessi[c]:,} | {r['totale']:,.0f} | {r['totale']/tot:.0%} | "
                 f"{r['attesa']/tot:.1%} | {r['processo']/tot:.1%} | {r['boarding']/tot:.1%} |".replace(",", "."))
    sf = {f: sum(r[f] for r in righe.values()) for f in fasi}
    L.append(f"| **Totale** | {asl.totale:,} | {tot:,.0f} | 100% | **{sf['attesa']/tot:.0%}** | "
             f"**{sf['processo']/tot:.0%}** | **{sf['boarding']/tot:.0%}** |".replace(",", "."))
    L.append("")
    L.append("Tetto teorico per ogni fase (se la si azzerasse del tutto):")
    for f in fasi:
        ok = "basta da sola" if sf[f] / tot >= target else "NON basta da sola"
        L.append(f"- {f}: -{sf[f]/tot:.0%} → {ok} per il -{target:.0%}")
    minori = sum(righe[c]["totale"] for c in (4, 5)) / tot
    L.append(f"- tutti i codici 4-5 insieme (fast track, CAU, see & treat): al massimo -{minori:.0%}")
    return "\n".join(L)


if __name__ == "__main__":
    import sys
    print(testo(float(sys.argv[1]) if len(sys.argv) > 1 else None))
