"""Metodo degli analoghi: previsione delle prossime ore a partire dallo stato osservato.

Dipende solo da numpy (e dalla libreria standard): lo usa anche la GitHub Action che pubblica
la previsione su pspratolive.it ogni 15 minuti, senza installare SimPy/SciPy.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime

import numpy as np

CODICI = [1, 2, 3, 4, 5]

def profilo_modello(lib):
    """Presenti e in attesa medi per ora del giorno nella libreria simulata."""
    T = np.concatenate([x[0] for x in lib]) % 24
    P = np.concatenate([x[1].sum(1) + x[2].sum(1) for x in lib])
    A = np.concatenate([x[1].sum(1) for x in lib])
    h = T.astype(int)
    return (np.array([P[h == i].mean() for i in range(24)]), np.array([A[h == i].mean() for i in range(24)]))


def profilo_reale(serie, fino_a=None):
    """Presenti e in attesa medi per ora del giorno nei dati osservati (eventualmente fino a una data)."""
    P = defaultdict(list); A = defaultdict(list)
    for ts, v in serie.items():
        t = datetime.fromisoformat(ts)
        if fino_a and t >= fino_a:
            continue
        a = sum(v["attesa"].values())
        P[t.hour].append(a + sum(v["tratt"].values())); A[t.hour].append(a)
    return (np.array([np.mean(P[h]) for h in range(24)]), np.array([np.mean(A[h]) for h in range(24)]))


def prevedi_analoghi(lib, stato, ora_del_giorno, orizzonte=12, k=60, tau=24.0,
                     percentili=(10, 50, 90), finestra_ore=1.0, correzione=None, allarga=1.0):
    """correzione: (profilo_reale, profilo_modello) -> si aggiunge la differenza di forma oraria.
    allarga: fattore sulla distanza dei percentili dalla mediana (tarato con il backtest)."""
    """k stati simulati più simili (stessa ora ± finestra, presenze per codice) e il loro futuro.
    Correzione di livello: differenza osservato-analogo, che si attenua con costante tau (ore)."""
    oss = np.array([[stato["attesa"].get(c, 0) for c in CODICI],
                    [stato["tratt"].get(c, 0) for c in CODICI]], dtype=float)
    passi = int(round(orizzonte * 4))
    cand = []
    for ir, (T, A, R) in enumerate(lib):
        ore = T % 24
        d_ora = np.abs((ore - ora_del_giorno + 12) % 24 - 12)
        idx = np.where((d_ora <= finestra_ore) & (np.arange(len(T)) + passi < len(T)))[0]
        if not len(idx):
            continue
        # distanza: per codice, in trattamento e in attesa (l'attesa pesa di più: cambia in fretta)
        dA = (A[idx] - oss[0]) / 3.0
        dR = (R[idx] - oss[1]) / np.sqrt(np.maximum(oss[1], 4))
        dist = np.sqrt((dA ** 2).sum(1) + (dR ** 2).sum(1))
        for i, dd in zip(idx, dist):
            cand.append((dd, ir, i))
    cand.sort(key=lambda x: x[0])
    scelti = cand[:k]
    ore_out = np.arange(passi + 1) / 4
    decad = np.exp(-ore_out / tau)[:, None]
    PA, PR = [], []
    for _, ir, i in scelti:
        T, A, R = lib[ir]
        fa = A[i:i + passi + 1].astype(float)
        fr = R[i:i + passi + 1].astype(float)
        fa = np.maximum(fa + (oss[0] - A[i]) * decad, 0)
        fr = np.maximum(fr + (oss[1] - R[i]) * decad, 0)
        PA.append(fa); PR.append(fr)
    PA, PR = np.stack(PA), np.stack(PR)
    pres = PA.sum(2) + PR.sum(2)
    att = PA.sum(2)
    if correzione is not None:
        (pr_r, at_r), (pr_m, at_m) = correzione
        hh = ((ora_del_giorno + ore_out) % 24).astype(int)
        h0 = int(ora_del_giorno) % 24
        d_pr = (pr_r[hh] - pr_m[hh]) - (pr_r[h0] - pr_m[h0])
        d_at = (at_r[hh] - at_m[hh]) - (at_r[h0] - at_m[h0])
        pres = np.maximum(pres + d_pr, 0)
        att = np.maximum(att + d_at, 0)
    def pct(x):
        q = {p: np.percentile(x, p, axis=0) for p in set(percentili) | {50}}
        return {str(p): (q[50] + allarga * (q[p] - q[50])).clip(0).tolist() for p in percentili}
    return dict(
        ore=ore_out.tolist(), presenti=pct(pres), in_attesa=pct(att),
        per_codice={c: pct(PA[:, :, i] + PR[:, :, i]) for i, c in enumerate(CODICI)},
        attesa_codice={c: pct(PA[:, :, i]) for i, c in enumerate(CODICI)},
        prob_oltre={str(s): (pres > s).mean(0).tolist() for s in (83, 120, 150)},
        distanza_media=float(np.mean([x[0] for x in scelti])),
    )
