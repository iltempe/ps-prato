"""Caricamento dati: ASL (accesso civico) + presenze misurate ogni 15 min (pspratolive.it).

Tutto ciò che il modello usa come "verità" da riprodurre passa da qui.
"""
from __future__ import annotations

import csv
import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from scipy import optimize, stats

def _radice_repo():
    """Cartella che contiene data/ufficiali (il modello può stare ovunque dentro il repo)."""
    for p in Path(__file__).resolve().parents:
        if (p / "data" / "ufficiali").is_dir():
            return p
    raise FileNotFoundError("cartella data/ufficiali non trovata")


ROOT = _radice_repo()
GEMELLO = Path(__file__).resolve().parent.parent      # gemello/: config, leve, output, ui
UFF = ROOT / "data" / "ufficiali"
PRESENZE = ROOT / "data" / "presenze.csv"
OSPEDALE = "Prato - Nuovo Ospedale S. Stefano"

CODICI = [1, 2, 3, 4, 5]
NOMI = {1: "Emergenza", 2: "Urg. indifferibile", 3: "Urg. differibile",
        4: "Urg. minore", 5: "Non urgenza"}
# Corrispondenza colori del feed -> codici numerici. Non dichiarata dalla fonte:
# ricavata verificando con la Legge di Little che presenze medie per colore
# ≈ accessi × permanenza ASL per codice (vedi verifica_colori()).
COLORE_CODICE = {"rosso": 1, "giallo": 2, "verde": 3, "azzurro": 4, "bianco": 5}


def durata_ore(s: str) -> float:
    m = re.match(r"\s*(\d+)h\s*(\d+)m", s)
    if not m:
        raise ValueError(f"durata non riconosciuta: {s!r}")
    return int(m.group(1)) + int(m.group(2)) / 60


def perc(s: str) -> float:
    return float(s.strip().rstrip("%")) / 100


def _righe(nome):
    with open(UFF / nome, newline="", encoding="utf-8") as f:
        return list(csv.reader(f))


def _blocco_per_codice(righe, anno, col_offset=0, start=0):
    """Trova la riga degli anni a partire da `start` e legge le righe '1. ...'..'5. ...'."""
    for i in range(start, len(righe)):
        r = righe[i]
        anni = [c.strip() for c in r[col_offset:]]
        if str(anno) in anni:
            j = col_offset + anni.index(str(anno))
            out = {}
            for r2 in righe[i + 1:]:
                lab = r2[col_offset].strip() if len(r2) > col_offset else ""
                m = re.match(r"(\d)\.", lab)
                if m:
                    out[int(m.group(1))] = r2[j]
                elif lab.startswith("Totale"):
                    out["tot"] = r2[j]
                    return out, i
                elif out:
                    return out, i
    raise ValueError("blocco non trovato")


@dataclass
class DatiASL:
    anno: int
    accessi: dict           # codice -> accessi annui
    permanenza: dict        # codice -> ore medie
    p8: dict                # codice -> quota > 8h
    p24: dict               # codice -> quota > 24h
    boarding_n: int
    boarding_ore: float
    abbandoni: int
    accessi_storici: dict   # anno -> totale accessi
    risorse: dict

    @property
    def totale(self):
        return sum(self.accessi.values())

    @property
    def ore_paziente(self):
        return {c: self.accessi[c] * self.permanenza[c] for c in CODICI}


def carica_asl(anno: int = 2025) -> DatiASL:
    r1 = _righe("01_accessi_per_codice_triage.csv")
    acc, _ = _blocco_per_codice(r1, anno)
    storici = {}
    hdr = r1[1]
    for k, a in enumerate(hdr):
        if a.strip().isdigit():
            tot_row = next(r for r in r1 if r and r[0].startswith("Totale"))
            v = tot_row[k].strip()
            if v not in ("-", ""):
                storici[int(a)] = int(v)

    perm, _ = _blocco_per_codice(_righe("02_tempo_permanenza_per_codice.csv"), anno)
    r3 = _righe("03_accessi_oltre_8h_24h.csv")
    p8, i8 = _blocco_per_codice(r3, anno, col_offset=9)
    p24, _ = _blocco_per_codice(r3, anno, col_offset=9, start=i8 + 3)

    def _o_none(f, v):
        v = v.strip()
        return None if v in ("-", "") else f(v)

    r4 = _righe("04_boarding.csv")
    j = [c.strip() for c in r4[2]].index(str(anno))
    b_n = _o_none(int, r4[3][j])
    b_ore = _o_none(durata_ore, r4[7][j])

    r5 = _righe("05_abbandoni.csv")
    j = [c.strip() for c in r5[2]].index(str(anno))
    abb = _o_none(int, r5[3][j])

    ris = {r[0].strip(): r[1].strip() for r in _righe("06_risorse.csv")[1:] if r}

    return DatiASL(
        anno=anno,
        accessi={c: int(acc[c]) for c in CODICI},
        permanenza={c: durata_ore(perm[c]) for c in CODICI},
        p8={c: perc(p8[c]) for c in CODICI},
        p24={c: perc(p24[c]) for c in CODICI},
        boarding_n=b_n, boarding_ore=b_ore, abbandoni=abb,
        accessi_storici=storici, risorse=ris,
    )


# --------------------------------------------------------------------------- #
# Presenze misurate
# --------------------------------------------------------------------------- #
@dataclass
class Presenze:
    inizio: str
    fine: str
    n: int
    tot_ora: np.ndarray            # 24: presenti medi per ora del giorno
    attesa_ora: np.ndarray         # 24: in attesa medi per ora del giorno
    attesa_codice: dict            # codice -> in attesa medi
    tratt_codice: dict             # codice -> in trattamento medi
    serie_tot: np.ndarray = field(repr=False)  # tutte le rilevazioni (presenti)

    @property
    def media(self):
        return float(self.serie_tot.mean())


def carica_presenze(path: Path = PRESENZE) -> Presenze:
    tot_h = defaultdict(list)
    att_h = defaultdict(list)
    att_c = defaultdict(list)
    tr_c = defaultdict(list)
    serie, ts = [], []
    with open(path, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["ospedale"] != OSPEDALE:
                continue
            a, t = int(r["in_attesa"]), int(r["in_trattamento"])
            cod = r["codice"]
            if cod == "totali":
                h = int(r["ts_scrape"][11:13])
                tot_h[h].append(a + t)
                att_h[h].append(a)
                serie.append(a + t)
                ts.append(r["ts_scrape"])
            elif cod in COLORE_CODICE:
                c = COLORE_CODICE[cod]
                att_c[c].append(a)
                tr_c[c].append(t)
    return Presenze(
        inizio=min(ts), fine=max(ts), n=len(serie),
        tot_ora=np.array([np.mean(tot_h[h]) for h in range(24)]),
        attesa_ora=np.array([np.mean(att_h[h]) for h in range(24)]),
        attesa_codice={c: float(np.mean(att_c[c])) for c in CODICI},
        tratt_codice={c: float(np.mean(tr_c[c])) for c in CODICI},
        serie_tot=np.array(serie, dtype=float),
    )


def verifica_colori(asl: DatiASL, pr: Presenze):
    """Little per codice: presenti attesi (ASL) vs misurati (feed)."""
    out = {}
    for c in CODICI:
        atteso = asl.accessi[c] * asl.permanenza[c] / 8760
        misurato = pr.attesa_codice[c] + pr.tratt_codice[c]
        out[c] = (atteso, misurato)
    return out


# --------------------------------------------------------------------------- #
# Distribuzione della permanenza per codice
# --------------------------------------------------------------------------- #
T_MAX = 120.0  # ore: permanenza massima plausibile (troncamento)


def _momenti_lognorm_tronc(mu, s, tmax=T_MAX):
    d = stats.lognorm(s=s, scale=math.exp(mu))
    Fmax = d.cdf(tmax)
    # media troncata: E[X | X<tmax]
    mean = math.exp(mu + s * s / 2) * stats.norm.cdf((math.log(tmax) - mu - s * s) / s) / Fmax
    p8 = (Fmax - d.cdf(8)) / Fmax
    p24 = (Fmax - d.cdf(24)) / Fmax
    return mean, p8, p24


def fit_permanenza(mean, p8, p24):
    """Lognormale troncata a T_MAX che riproduce media, quota>8h e quota>24h (minimi quadrati)."""
    def err(x):
        mu, ls = x
        m, a, b = _momenti_lognorm_tronc(mu, math.exp(ls))
        # la media pesa di più: è quella che determina le ore-paziente (Little)
        return [3 * (m - mean) / mean, (a - p8) / max(p8, 0.01), (b - p24) / max(p24, 0.01)]
    best = None
    lb, ub = [-2.0, math.log(0.1)], [5.0, math.log(3.0)]
    for mu0 in (0.5, 1.5, 2.5):
        for s0 in (0.5, 1.0, 1.5):
            r = optimize.least_squares(err, [mu0, math.log(s0)], bounds=(lb, ub))
            if best is None or r.cost < best.cost:
                best = r
    mu, s = best.x[0], math.exp(best.x[1])
    return mu, s, _momenti_lognorm_tronc(mu, s)


def anni_disponibili():
    """Anni con dati ASL (il 2019 non è recuperabile dal sistema aziendale)."""
    return [a for a in range(2019, 2100) if _anno_ok(a)]


def _anno_ok(a):
    try:
        carica_asl(a)
        return True
    except (ValueError, KeyError, IndexError):
        return False


if __name__ == "__main__":
    asl = carica_asl()
    pr = carica_presenze()
    print(f"ASL {asl.anno}: {asl.totale} accessi, boarding {asl.boarding_n} × {asl.boarding_ore:.1f}h")
    print(f"Presenze {pr.inizio} → {pr.fine}, n={pr.n}, media {pr.media:.1f}")
    for c, (a, m) in verifica_colori(asl, pr).items():
        print(f"  codice {c}: atteso {a:5.1f}  misurato {m:5.1f}")
    for c in CODICI:
        mu, s, (m, a, b) = fit_permanenza(asl.permanenza[c], asl.p8[c], asl.p24[c])
        print(f"  fit {c}: media {m:5.1f}/{asl.permanenza[c]:5.1f}  >8h {a:.1%}/{asl.p8[c]:.1%}  >24h {b:.1%}/{asl.p24[c]:.1%}")
