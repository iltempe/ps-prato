"""Serie storiche ASL 2020-2025 e loro uso nel modello.

- serie(): tabella per anno e codice (accessi, permanenza, >8h, >24h, ore-paziente, quote)
- crescita_per_codice(): tasso medio annuo degli accessi per codice (per le proiezioni)
- validazione_storica(): il modello tarato su un anno deve riprodurre gli altri anni
  dandogli SOLO gli accessi di quell'anno. Se non ci riesce, vuol dire che tra un anno e
  l'altro non è cambiato solo il carico (es. letti, personale, organizzazione): un limite
  da conoscere prima di fidarsi delle proiezioni.
"""
from __future__ import annotations

import copy
from functools import lru_cache

import dati as D

ANNO_ANOMALO = 2021   # pandemia: l'ASL stessa invita alla cautela


@lru_cache(maxsize=None)
def carica_tutti():
    return {a: D.carica_asl(a) for a in D.anni_disponibili()}


def serie():
    out = {}
    for a, x in carica_tutti().items():
        ore = x.ore_paziente
        tot = sum(ore.values())
        out[a] = dict(
            accessi=x.accessi, totale=x.totale,
            permanenza=x.permanenza, p8=x.p8, p24=x.p24,
            permanenza_media=tot / x.totale,
            quota_ore={c: ore[c] / tot for c in D.CODICI},
            # permanenza di ogni codice rispetto alla media: confronto tra codici
            rapporto_media={c: x.permanenza[c] / (tot / x.totale) for c in D.CODICI},
            presenti_little=tot / 8760,
            boarding_n=x.boarding_n, boarding_ore=x.boarding_ore,
            abbandoni=x.abbandoni,
            abbandoni_quota=(x.abbandoni / x.totale) if x.abbandoni else None,
            anomalo=a == ANNO_ANOMALO,
        )
    return out


def crescita_per_codice(da=2022, a=2025):
    t = carica_tutti()
    n = a - da
    return {c: (t[a].accessi[c] / t[da].accessi[c]) ** (1 / n) - 1 for c in D.CODICI}


def crescita_totale(da=2022, a=2025):
    t = carica_tutti()
    return (t[a].totale / t[da].totale) ** (1 / (a - da)) - 1


def validazione_storica(sc_base, anni=None, simula=None, valuta=None):
    """Per ogni anno: scenario tarato + accessi per codice di quell'anno.
    `valuta(lista_scenari) -> lista_risultati` permette l'esecuzione in parallelo."""
    import simulazione as S
    t = carica_tutti()
    anni = anni or [a for a in t if a != ANNO_ANOMALO]
    scen = []
    for a in anni:
        sc = copy.deepcopy(sc_base)
        sc.nome = f"storico_{a}"
        sc.arrivi_anno = {c: float(t[a].accessi[c]) for c in D.CODICI}
        scen.append(sc)
    if valuta:
        res = valuta(scen)
    else:
        res = [(simula or S.simula)(s) for s in scen]
    righe = []
    for a, r in zip(anni, res):
        x = t[a]
        tot_reale = sum(x.ore_paziente.values()) / x.totale
        righe.append(dict(
            anno=a, accessi=x.totale,
            permanenza_sim=r.permanenza, permanenza_reale=tot_reale,
            codici={c: dict(sim=r.permanenza_codice[c], reale=x.permanenza[c],
                            p24_sim=r.p24_codice[c] if hasattr(r, "p24_codice") else None,
                            p24_reale=x.p24[c]) for c in D.CODICI},
            boarding_sim=r.boarding_ore, boarding_reale=x.boarding_ore,
            stabile=r.stabile,
        ))
    return righe


if __name__ == "__main__":
    s = serie()
    print("anno  accessi  perm.  " + "  ".join(f"c{c}:perm(xmedia)" for c in D.CODICI))
    for a, v in s.items():
        print(f"{a}{'*' if v['anomalo'] else ' '} {v['totale']:7d}  {v['permanenza_media']:5.1f}h  " +
              "  ".join(f"{v['permanenza'][c]:5.1f}h({v['rapporto_media'][c]:.2f})" for c in D.CODICI))
    print("crescita accessi 2022-2025 per codice:",
          {c: f"{g:+.1%}" for c, g in crescita_per_codice().items()}, f"totale {crescita_totale():+.1%}")
