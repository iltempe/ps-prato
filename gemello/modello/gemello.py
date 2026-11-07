"""Gemello digitale: dallo stato reale del PS alle prossime ore.

1. Stato: ultima rilevazione (pspratolive.it/data/latest.json o data/presenze.csv):
   per ogni codice quanti sono in attesa e quanti in trattamento.
2. Ricostruzione di ciò che non si osserva:
   - chi è in trattamento: il tempo che gli resta è estratto dalla distribuzione del
     "tempo residuo" in un sistema a regime (densità ∝ probabilità di essere ancora in PS,
     dalla permanenza ASL per codice);
   - chi è in attesa: arrivato da un tempo casuale tra 0 e il doppio dell'attesa media misurata.
3. Simulazione delle prossime N ore, ripetuta molte volte -> forchetta (percentili).
4. Backtest: la stessa previsione fatta su ogni istante passato e confrontata con
   quello che è successo davvero, contro due previsioni banali (persistenza e media oraria).
"""
from __future__ import annotations

import copy
import csv
import json
import math
import random
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
from scipy import stats

import dati as D
import simulazione as S

URL_LIVE = "https://pspratolive.it/data/latest.json"


# --------------------------------------------------------------------------- #
# Stato osservato
# --------------------------------------------------------------------------- #
def stato_live(url=URL_LIVE, timeout=15):
    """Ultima rilevazione pubblicata su pspratolive.it per il Santo Stefano."""
    with urllib.request.urlopen(url, timeout=timeout) as r:
        j = json.load(r)
    for o in j["ospedali"]:
        if o["ospedale"] == D.OSPEDALE:
            cod = o["codici"]
            return dict(
                ts=o["ts"], fonte=url,
                attesa={D.COLORE_CODICE[k]: int(v["att"]) for k, v in cod.items() if k in D.COLORE_CODICE},
                tratt={D.COLORE_CODICE[k]: int(v["trt"]) for k, v in cod.items() if k in D.COLORE_CODICE},
            )
    raise ValueError("Santo Stefano non trovato nello snapshot")


def storico_osservato(path=D.PRESENZE, extra=None):
    """Serie completa per timestamp: {ts: {"attesa": {c: n}, "tratt": {c: n}}} ordinata.
    `extra`: rilevazioni aggiuntive (es. raccolte dal server dal live) nello stesso formato."""
    serie = defaultdict(lambda: {"attesa": {}, "tratt": {}})
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["ospedale"] != D.OSPEDALE or r["codice"] not in D.COLORE_CODICE:
                continue
            c = D.COLORE_CODICE[r["codice"]]
            serie[r["ts_scrape"]]["attesa"][c] = int(r["in_attesa"])
            serie[r["ts_scrape"]]["tratt"][c] = int(r["in_trattamento"])
    for ts, v in (extra or {}).items():
        serie[ts] = v
    return dict(sorted((k, v) for k, v in serie.items() if len(v["attesa"]) == 5))


def ore_dal_riferimento(ts: str, rif: datetime) -> float:
    return (datetime.fromisoformat(ts) - rif).total_seconds() / 3600


# --------------------------------------------------------------------------- #
# Tempo residuo per codice (equilibrio): densità ∝ S(r)
# --------------------------------------------------------------------------- #
_RESIDUI = {}


def campionatore_residui(sc):
    """Tempo residuo coerente con il modello: dalla permanenza dei pazienti simulati a regime
    con lo stesso scenario (non da una distribuzione teorica). Densità del residuo ∝ S(r)."""
    key = (sc.nome, round(sc.fattore_medico, 4), round(sum(sc.processo_scala.values()), 4),
           round(sc.letti_capacita_giorno, 3))
    if key not in _RESIDUI:
        s2 = copy.deepcopy(sc)
        s2.giorni = 120
        ps = S.PS(s2)
        ps.esegui()
        los = defaultdict(list)
        for c, _, durata, _, _, abb in ps.pazienti:
            if not abb:
                los[c].append(durata)
        g = np.linspace(0, D.T_MAX, 4801)
        tab = {}
        for c in D.CODICI:
            x = np.sort(np.array(los[c]))
            Sv = 1 - np.searchsorted(x, g, side="right") / len(x)
            cdf = np.cumsum(Sv)
            tab[c] = (g, cdf / cdf[-1])
        # quota di chi, tra i presenti in trattamento, sta aspettando un letto (boarding)
        perm = {c: np.mean(los[c]) for c in D.CODICI}
        r_b = 1 / (S.margine_letti(sc) / 24) if S.margine_letti(sc) > 0 else 24 * 30
        q_b = {c: min(0.9, sc.p_ricovero.get(c, 0) * r_b / perm[c]) for c in D.CODICI}
        _RESIDUI[key] = (tab, q_b)
    return _RESIDUI[key]


# --------------------------------------------------------------------------- #
# Una previsione
# --------------------------------------------------------------------------- #
def _una_corsa(args):
    sc, stato, ora_del_giorno, orizzonte, seed, attese_medie, (residui, q_board) = args
    sc = copy.deepcopy(sc)
    sc.warmup = 0
    sc.giorni = orizzonte / 24
    sc.seed = seed
    t0 = 24 * 7 + ora_del_giorno          # una settimana "fittizia" per avere t0 > 0
    ps = S.PS(sc, t0=t0)
    ps.traiettoria = []
    rng = random.Random(seed + 7)
    # chi è già in trattamento: resta per un tempo residuo; se non è in boarding, prima di
    # uscire passa dal medico per la rivalutazione/dimissione (occupa i medici come nella realtà)
    def in_corso(c, r, boarder):
        ps.tratt[c] += 1
        if boarder:
            yield ps.env.timeout(r)
        else:
            yield ps.env.timeout(max(0.0, r - sc.t_rival[c] * sc.fattore_medico))
            reqs = ps._richiesta_medico(c, rival=True)
            esito = yield S.simpy.AnyOf(ps.env, [q for _, q in reqs])
            presa = next(rr for rr in reqs if rr[1] in esito)
            for res2, q in reqs:
                if q is not presa[1]:
                    res2.release(q) if q.triggered else q.cancel()
            yield ps.env.timeout(ps._lognorm(sc.t_rival[c] * sc.fattore_medico, 0.6))
            presa[0].release(presa[1])
        ps.tratt[c] -= 1
    for c in D.CODICI:
        g, cdf = residui[c]
        for _ in range(stato["tratt"].get(c, 0)):
            r = float(np.interp(rng.random(), cdf, g))
            ps.env.process(in_corso(c, r, rng.random() < q_board[c]))
        for _ in range(stato["attesa"].get(c, 0)):
            gia = rng.uniform(0, 2 * attese_medie[c])
            ps.env.process(ps.paziente(c, t_arrivo=t0 - gia))
    ps.env.process(ps.arrivi())
    ps.env.process(ps.osserva())
    ps.env.run(until=t0 + orizzonte + 1e-6)
    T = np.array([x[0] - t0 for x in ps.traiettoria])
    A = np.array([x[1] for x in ps.traiettoria], dtype=float)
    R = np.array([x[2] for x in ps.traiettoria], dtype=float)
    return T, A, R


def prevedi(sc, stato, ora_del_giorno, orizzonte=12, repliche=50, percentili=(10, 50, 90),
            asl=None, pr=None, pool=None, seed=1):
    """Forchetta delle prossime `orizzonte` ore per presenti, in attesa e per codice."""
    asl = asl or D.carica_asl()
    pr = pr or D.carica_presenze()
    att_medie = {c: pr.attesa_codice[c] / (asl.accessi[c] / 8760) for c in D.CODICI}
    residui = campionatore_residui(sc)
    jobs = [(sc, stato, ora_del_giorno, orizzonte, seed + 101 * k, att_medie, residui)
            for k in range(repliche)]
    corse = list(pool.map(_una_corsa, jobs)) if pool else [_una_corsa(j) for j in jobs]
    n = min(len(c[0]) for c in corse)
    T = corse[0][0][:n]
    A = np.stack([c[1][:n] for c in corse])          # repliche × tempi × codici
    R = np.stack([c[2][:n] for c in corse])
    pres = A.sum(2) + R.sum(2)
    att = A.sum(2)
    def pct(x):
        return {str(p): np.percentile(x, p, axis=0).tolist() for p in percentili}
    return dict(
        ore=T.tolist(),
        presenti=pct(pres), in_attesa=pct(att),
        per_codice={c: pct(A[:, :, i] + R[:, :, i]) for i, c in enumerate(D.CODICI)},
        prob_oltre={str(s): (pres > s).mean(0).tolist() for s in (83, 120, 150)},
    )


# --------------------------------------------------------------------------- #
# Backtest
# --------------------------------------------------------------------------- #
def opz_analoghi_prev(o):
    o = dict(o or {})
    return {k: o[k] for k in ("k", "tau", "finestra_ore", "allarga") if k in o}


def backtest(sc, giorni=30, ogni_ore=3, orizzonte=12, repliche=20, pool=None, progresso=None,
             asl=None, pr=None, extra=None, metodo="analoghi", opz_analoghi=None):
    asl = asl or D.carica_asl()
    pr = pr or D.carica_presenze()
    serie = storico_osservato(extra=extra)
    ts = list(serie)
    tempi = [datetime.fromisoformat(t) for t in ts]
    tot = np.array([sum(serie[t]["attesa"].values()) + sum(serie[t]["tratt"].values()) for t in ts], float)
    att = np.array([sum(serie[t]["attesa"].values()) for t in ts], float)
    # media oraria (climatologia) calcolata solo sul periodo PRIMA del backtest, per onestà
    fine = tempi[-1]
    inizio = fine - timedelta(days=giorni)
    prima = [i for i, t in enumerate(tempi) if t < inizio]
    base_idx = prima if len(prima) > 24 * 4 * 7 else list(range(len(ts)))
    clim_tot = np.zeros(24); clim_att = np.zeros(24)
    for h in range(24):
        idx = [i for i in base_idx if tempi[i].hour == h]
        clim_tot[h] = tot[idx].mean(); clim_att[h] = att[idx].mean()

    origini = []
    t_next = inizio
    for i, t in enumerate(tempi):
        if t >= t_next and t + timedelta(hours=orizzonte) <= fine:
            origini.append(i)
            t_next = t + timedelta(hours=ogni_ore)

    orizzonti = [1, 3, 6, 12] if orizzonte >= 12 else [h for h in (1, 3, 6) if h <= orizzonte]
    err = {k: {h: [] for h in orizzonti} for k in
           ("gemello_tot", "persist_tot", "clim_tot", "gemello_att", "persist_att", "clim_att")}
    dentro = {h: [] for h in orizzonti}
    for n_o, i in enumerate(origini):
        t0 = tempi[i]
        stato = dict(attesa=serie[ts[i]]["attesa"], tratt=serie[ts[i]]["tratt"])
        if metodo == "analoghi":
            if n_o == 0:
                o = dict(opz_analoghi or {})
                lib = libreria_analoghi(sc, o.pop("giorni", 180), o.pop("repliche", 8), pool)
                corr = None
                if (opz_analoghi or {}).get("correzione_profilo", True):
                    # profilo reale calcolato solo PRIMA del periodo di test (niente sbirciate)
                    corr = (profilo_reale(serie, fino_a=inizio), profilo_modello(lib))
            p = prevedi_analoghi(lib, stato, t0.hour + t0.minute / 60, orizzonte, correzione=corr,
                                 **(opz_analoghi_prev(opz_analoghi)))
        else:
            p = prevedi(sc, stato, t0.hour + t0.minute / 60, orizzonte, repliche, asl=asl, pr=pr,
                        pool=pool, seed=1000 + n_o)
        ore = np.array(p["ore"])
        for h in orizzonti:
            bersaglio = t0 + timedelta(hours=h)
            j = min(range(i, min(i + 4 * h + 12, len(tempi))), key=lambda k: abs((tempi[k] - bersaglio).total_seconds()))
            if abs((tempi[j] - bersaglio).total_seconds()) > 1800:
                continue
            k = int(np.argmin(np.abs(ore - h)))
            m_tot, m_att = p["presenti"]["50"][k], p["in_attesa"]["50"][k]
            err["gemello_tot"][h].append(abs(m_tot - tot[j]))
            err["persist_tot"][h].append(abs(tot[i] - tot[j]))
            # climatologia "ancorata": profilo medio orario spostato al livello attuale
            err["clim_tot"][h].append(abs(clim_tot[bersaglio.hour] + (tot[i] - clim_tot[t0.hour]) - tot[j]))
            err["gemello_att"][h].append(abs(m_att - att[j]))
            err["persist_att"][h].append(abs(att[i] - att[j]))
            err["clim_att"][h].append(abs(clim_att[bersaglio.hour] - att[j]))
            dentro[h].append(p["presenti"]["10"][k] <= tot[j] <= p["presenti"]["90"][k])
        if progresso:
            progresso((n_o + 1) / len(origini), f"{n_o+1}/{len(origini)} previsioni")
    return dict(
        periodo=[inizio.isoformat(), fine.isoformat()], n_previsioni=len(origini),
        orizzonti=orizzonti,
        mae={k: {h: float(np.mean(v)) if v else None for h, v in d.items()} for k, d in err.items()},
        copertura_80={h: float(np.mean(v)) if v else None for h, v in dentro.items()},
        metodo=metodo,
    )


if __name__ == "__main__":
    import sys, time
    cfg = S.carica_config()
    var = cfg['turni_medici']['scenario'] + ("_rivprec" if cfg.get("rivalutazione_precedenza") else "")
    sc = S.carica_scenario(D.GEMELLO / "output" / f"scenario_{var}.yaml")
    st = stato_live()
    t = datetime.fromisoformat(st["ts"])
    print("stato live", st["ts"], "presenti", sum(st["attesa"].values()) + sum(st["tratt"].values()))
    t1 = time.time()
    p = prevedi(sc, st, t.hour + t.minute / 60, 12, 30)
    print(f"previsione in {time.time()-t1:.1f}s")
    for h in (0, 1, 3, 6, 12):
        k = int(np.argmin(np.abs(np.array(p["ore"]) - h)))
        print(f"  +{h:2d}h presenti {p['presenti']['10'][k]:.0f}-{p['presenti']['90'][k]:.0f} "
              f"(mediana {p['presenti']['50'][k]:.0f}), in attesa {p['in_attesa']['50'][k]:.0f}")


# --------------------------------------------------------------------------- #
# Metodo degli analoghi (default): funzioni in analoghi.py (solo numpy)
from analoghi import prevedi_analoghi, profilo_modello, profilo_reale  # noqa: E402,F401
# --------------------------------------------------------------------------- #
_LIBRERIE = {}


def _traiettoria_lunga(sc):
    ps = S.PS(sc)
    ps.traiettoria = []
    ps.esegui()
    tr = [x for x in ps.traiettoria if ps.t_inizio <= x[0] <= ps.t_fine]
    return (np.array([x[0] for x in tr]), np.array([x[1] for x in tr], dtype=np.int16),
            np.array([x[2] for x in tr], dtype=np.int16))


def chiave_scenario(sc):
    import hashlib
    from dataclasses import asdict
    def canon(x):                           # 1736 e 1736.0 devono dare la stessa impronta
        if isinstance(x, bool) or x is None or isinstance(x, str):
            return x
        if isinstance(x, (int, float)):
            return round(float(x), 9)
        if isinstance(x, dict):
            return {str(k): canon(v) for k, v in x.items()}
        return [canon(v) for v in x]
    d = canon(S._puro(asdict(sc)))
    d.pop("nome", None)                     # il nome non cambia il modello
    return hashlib.md5(json.dumps(d, sort_keys=True, default=str).encode()).hexdigest()


def libreria_analoghi(sc, giorni=180, repliche=8, pool=None):
    """Lunga simulazione a regime (più semi) con la traiettoria ogni 15 minuti."""
    key = (chiave_scenario(sc), giorni, repliche)
    if key not in _LIBRERIE:
        scen = []
        for k in range(repliche):
            s2 = copy.deepcopy(sc)
            s2.giorni = giorni
            s2.seed = sc.seed + 7919 * (k + 1)
            scen.append(s2)
        corse = list(pool.map(_traiettoria_lunga, scen)) if pool else [_traiettoria_lunga(s) for s in scen]
        _LIBRERIE[key] = corse
    return _LIBRERIE[key]

