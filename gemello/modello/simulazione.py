"""Simulazione a eventi discreti del PS Santo Stefano (SimPy).

Percorso del paziente:
  arrivo -> attesa prima visita (coda medici con priorità per codice, abbandono possibile)
         -> visita -> processo (esami, consulenze, osservazione: non occupa il medico)
         -> rivalutazione/dimissione (medico) -> [se ricovero] boarding fino a un letto libero
         -> uscita

Calibrazione (vedi calibra()):
  - arrivi orari: deconvoluzione della curva delle presenze misurate (pspratolive.it)
  - fattore tempo medico: riproduce le persone in attesa misurate
  - posti letto liberati al giorno: riproduce l'attesa media di boarding ASL
  - durata del processo per codice: riproduce la permanenza media ASL per codice
  - pazienza: riproduce il tasso di abbandono ASL
"""
from __future__ import annotations

import copy
import heapq
import math
import random
from dataclasses import dataclass, field, asdict
from pathlib import Path

import numpy as np
import simpy
import yaml
from scipy import optimize

import dati as D

QUI = D.GEMELLO


def carica_config():
    with open(QUI / "config.yaml") as f:
        return yaml.safe_load(f)


def fasce_in_orario(fasce: dict) -> np.ndarray:
    """{"20-02": 4, ...} -> array di 24 valori (medici per ora)."""
    out = np.zeros(24, dtype=int)
    for k, n in fasce.items():
        a, b = (int(x) for x in k.split("-"))
        h = a
        while True:
            out[h % 24] += n
            h = (h + 1) % 24
            if h == b % 24:
                break
    return out


# --------------------------------------------------------------------------- #
# Parametri di una simulazione
# --------------------------------------------------------------------------- #
@dataclass
class Scenario:
    nome: str
    arrivi_anno: dict                 # codice -> accessi/anno
    profilo_arrivi: list              # 24 pesi (media 1)
    medici_ora: list                  # 24 interi
    t_visita: dict                    # codice -> ore medico
    t_rival: dict
    fattore_medico: float
    processo_mu: dict                 # codice -> mu della lognormale di permanenza (fit ASL)
    processo_sigma: dict              # codice -> sigma
    processo_scala: dict              # codice -> moltiplicatore (1 = calibrato; le leve lo riducono)
    p_ricovero: dict
    pazienza: dict                    # codice -> ore medie (assente = non abbandona)
    # Letti di reparto (coda a molti serventi): l'attesa di un letto, per chi aspetta,
    # è esponenziale con media 1 / (capacità − domanda) [Erlang C].
    letti_capacita_giorno: float      # letti che si liberano al giorno (reparti che ricevono dal PS)
    ricoveri_altri_giorno: float      # ricoveri negli stessi reparti non provenienti dal PS
    # margine (ore) della scadenza "da vedere entro": priorità = arrivo + margine.
    # Ricavato dalle attese misurate per codice; il codice 1 passa sempre davanti.
    rival_precedenza: bool = False    # True: la rivalutazione passa davanti ai nuovi arrivi
    priorita: dict = field(default_factory=lambda: {1: -1e6, 2: 0.5, 3: 2.0, 4: 1.2, 5: 0.4})
    # leve opzionali
    ft_ora: list = field(default_factory=lambda: [0] * 24)   # medici fast track per ora
    ft_codici: tuple = ()
    ft_riduzione_processo: float = 0.0
    # Due percorsi dopo la visita (per codice): breve (dimissione in poche ore) o lungo
    # (osservazione, consulenze, attesa di posto). Calibrati su media, quota >8h e >24h ASL.
    lungo_quota: dict = field(default_factory=dict)
    lungo_mediana: dict = field(default_factory=dict)
    lungo_sigma: dict = field(default_factory=dict)
    breve_mediana: dict = field(default_factory=dict)
    giorni: int = 182
    warmup: int = 21
    seed: int = 42


# --------------------------------------------------------------------------- #
# Modello
# --------------------------------------------------------------------------- #
class Medici:
    """Pool di medici con numero variabile per ora: i medici fuori turno sono
    'occupati' da richieste fittizie a priorità massima (finiscono il paziente in corso)."""

    def __init__(self, env, orario):
        self.env = env
        self.orario = list(orario)
        self.cap = max(1, max(self.orario))
        self.res = simpy.PriorityResource(env, capacity=self.cap)
        self.blocchi = []
        env.process(self._turni())

    def _turni(self):
        env = self.env
        while True:
            h = int(env.now) % 24
            da_bloccare = self.cap - self.orario[h]
            while len(self.blocchi) < da_bloccare:
                self.blocchi.append(self.res.request(priority=-1e12))
            while len(self.blocchi) > da_bloccare:
                req = self.blocchi.pop()
                if req.triggered:
                    self.res.release(req)
                else:
                    req.cancel()
            yield env.timeout(math.floor(env.now) + 1 - env.now)


class PS:
    def __init__(self, sc: Scenario, t0: float | None = None):
        """t0: ora di partenza (ore, con ora del giorno = t0 % 24). Se assente: simulazione a
        regime con warmup. Con t0 il PS parte vuoto e lo stato iniziale si inietta con inietta()."""
        self.sc = sc
        self.env = simpy.Environment(initial_time=t0 or 0)
        self.rng = random.Random(sc.seed)
        self.medici = Medici(self.env, sc.medici_ora)
        self.ft = Medici(self.env, sc.ft_ora) if any(sc.ft_ora) else None
        self.coda_letti = []      # heap (codice, t, seq, evento)
        self.seq = 0
        self.attesa = {c: 0 for c in D.CODICI}
        self.tratt = {c: 0 for c in D.CODICI}
        self.pazienti = []        # (codice, t_arrivo, permanenza, attesa_visita, boarding, abbandono)
        self.censimento = []      # (ora_del_giorno, in_attesa, in_trattamento)
        self.t_inizio = sc.warmup * 24 if t0 is None else t0
        self.t_fine = self.t_inizio + sc.giorni * 24
        self.traiettoria = None   # se lista: registra (t, attesa per codice, trattamento per codice)
        self.margine_letti_ora = margine_letti(sc) / 24

    # -- utilità -------------------------------------------------------------
    def _lognorm(self, media, sigma):
        mu = math.log(media) - sigma * sigma / 2
        return self._lognorm_mu(mu, sigma)

    def _lognorm_mu(self, mu, sigma):
        while True:
            x = self.rng.lognormvariate(mu, sigma)
            if x < D.T_MAX:
                return x

    def durata_processo(self, c):
        sc = self.sc
        if sc.lungo_quota:
            if self.rng.random() < sc.lungo_quota[c]:
                return self._lognorm_mu(math.log(sc.lungo_mediana[c]), sc.lungo_sigma[c])
            return self._lognorm_mu(math.log(sc.breve_mediana[c]), 0.7)
        return self._lognorm_mu(sc.processo_mu[c], sc.processo_sigma[c])

    def _richiesta_medico(self, c, rival=False, t_base=None):
        """Richiede un medico dal pool generale o, se previsto, dal fast track: vince il primo libero."""
        p = (self.env.now if t_base is None else t_base) + self.sc.priorita[c]
        if rival and self.sc.rival_precedenza:
            p = -1e6 + self.env.now
        if self.ft and c in self.sc.ft_codici:
            r1 = self.medici.res.request(priority=p)
            r2 = self.ft.res.request(priority=p)
            return [(self.medici.res, r1), (self.ft.res, r2)]
        return [(self.medici.res, self.medici.res.request(priority=p))]

    # -- processi ------------------------------------------------------------
    def arrivi(self):
        sc = self.sc
        tot = sum(sc.arrivi_anno.values())
        tasso_medio = tot / 8760
        prof = np.array(sc.profilo_arrivi)
        lmax = tasso_medio * prof.max()
        codici = list(sc.arrivi_anno)
        pesi = [sc.arrivi_anno[c] for c in codici]
        while True:
            yield self.env.timeout(self.rng.expovariate(lmax))
            if self.env.now > self.t_fine:
                return
            h = int(self.env.now) % 24
            if self.rng.random() < prof[h] / prof.max():   # thinning (Poisson non omogeneo)
                c = self.rng.choices(codici, pesi)[0]
                self.env.process(self.paziente(c))

    def paziente(self, c, t_arrivo=None):
        env, sc = self.env, self.sc
        t0 = env.now if t_arrivo is None else t_arrivo
        self.attesa[c] += 1
        reqs = self._richiesta_medico(c, t_base=t0)
        eventi = [r for _, r in reqs]
        if c in sc.pazienza:
            paz = env.timeout(self.rng.expovariate(1 / sc.pazienza[c]))
            esito = yield simpy.AnyOf(env, eventi + [paz])
        else:
            esito = yield simpy.AnyOf(env, eventi)
        presa = next(((res, r) for res, r in reqs if r in esito), None)
        for res, r in reqs:                       # libera le altre richieste
            if presa is None or r is not presa[1]:
                if r.triggered:
                    res.release(r)
                else:
                    r.cancel()
        self.attesa[c] -= 1
        attesa_visita = env.now - t0
        if presa is None:                         # abbandono prima della visita
            self._registra(c, t0, attesa_visita, 0.0, True)
            return
        self.tratt[c] += 1
        res, req = presa
        fast = self.ft is not None and res is self.ft.res
        yield env.timeout(self._lognorm(sc.t_visita[c] * sc.fattore_medico, 0.6))
        res.release(req)

        scala = sc.processo_scala[c] * (1 - (sc.ft_riduzione_processo if fast else 0))
        yield env.timeout(scala * self.durata_processo(c))

        reqs = self._richiesta_medico(c, rival=True)
        esito = yield simpy.AnyOf(env, [r for _, r in reqs])
        presa = next((rr for rr in reqs if rr[1] in esito))
        for res2, r in reqs:
            if r is not presa[1]:
                if r.triggered:
                    res2.release(r)
                else:
                    r.cancel()
        yield env.timeout(self._lognorm(sc.t_rival[c] * sc.fattore_medico, 0.6))
        presa[0].release(presa[1])

        boarding = 0.0
        if self.rng.random() < sc.p_ricovero.get(c, 0):
            margine = self.margine_letti_ora
            boarding = self.rng.expovariate(margine) if margine > 0 else 24 * 30
            boarding = min(boarding, 24 * 30)
            yield env.timeout(boarding)
        self.tratt[c] -= 1
        self._registra(c, t0, attesa_visita, boarding, False)

    def osserva(self):
        while True:
            if self.traiettoria is not None:
                self.traiettoria.append((self.env.now, tuple(self.attesa[c] for c in D.CODICI),
                                         tuple(self.tratt[c] for c in D.CODICI)))
            yield self.env.timeout(0.25)
            if self.t_inizio <= self.env.now <= self.t_fine:
                self.censimento.append((int(self.env.now) % 24,
                                        sum(self.attesa.values()), sum(self.tratt.values()),
                                        tuple(self.attesa[c] + self.tratt[c] for c in D.CODICI),
                                        tuple(self.attesa[c] for c in D.CODICI)))

    def _registra(self, c, t0, attesa, boarding, abbandono):
        if self.t_inizio <= t0 <= self.t_fine:
            self.pazienti.append((c, t0, self.env.now - t0, attesa, boarding, abbandono))

    def esegui(self):
        self.env.process(self.arrivi())
        self.env.process(self.osserva())
        # dopo la fine degli arrivi lascio uscire chi è ancora dentro (fino a 5 giorni)
        self.env.run(until=self.t_fine + 5 * 24)
        return Risultato.da(self)


@dataclass
class Risultato:
    nome: str
    permanenza: float
    permanenza_codice: dict
    p8: float
    p24: float
    p8_codice: dict
    p24_codice: dict
    attesa_visita: float
    attesa_visita_codice: dict
    in_attesa: float
    presenti: float
    presenti_codice: dict
    presenti_ora: list
    in_attesa_ora: list
    boarding_n_anno: float
    boarding_ore: float
    abbandoni_quota: float
    quota_tempo_oltre_83: float
    accessi_anno: float
    deriva: float = 1.0      # presenti ultimo quarto / primo quarto della simulazione (>1.15 = non stazionario)
    # dettaglio per codice di triage
    accessi_codice: dict = field(default_factory=dict)
    in_attesa_codice: dict = field(default_factory=dict)
    boarding_n_codice: dict = field(default_factory=dict)
    boarding_ore_codice: dict = field(default_factory=dict)
    abbandoni_codice: dict = field(default_factory=dict)

    @property
    def stabile(self):
        return self.deriva < 1.15

    @staticmethod
    def da(ps: PS):
        P = np.array([(c, los, att, b, ab) for c, _, los, att, b, ab in ps.pazienti], dtype=float)
        C = ps.censimento
        anni = ps.sc.giorni / 365
        cod, los, att, bo, ab = P.T
        def per(c, v, f=np.mean):
            m = cod == c
            return float(f(v[m])) if m.any() else float("nan")
        ore = np.array([x[0] for x in C])
        ia = np.array([x[1] for x in C], dtype=float)
        pres = np.array([x[1] + x[2] for x in C], dtype=float)
        pc = np.array([x[3] for x in C], dtype=float)
        ac = np.array([x[4] for x in C], dtype=float)
        visti = ab == 0
        bmask = bo > 0
        return Risultato(
            nome=ps.sc.nome,
            permanenza=float(los.mean()),
            permanenza_codice={c: per(c, los) for c in D.CODICI},
            p8=float((los > 8).mean()), p24=float((los > 24).mean()),
            p8_codice={c: per(c, (los > 8).astype(float)) for c in D.CODICI},
            p24_codice={c: per(c, (los > 24).astype(float)) for c in D.CODICI},
            attesa_visita=float(att[visti].mean()),
            attesa_visita_codice={c: float(att[visti & (cod == c)].mean()) for c in D.CODICI},
            in_attesa=float(ia.mean()),
            presenti=float(pres.mean()),
            presenti_codice={c: float(pc[:, i].mean()) for i, c in enumerate(D.CODICI)},
            presenti_ora=[float(pres[ore == h].mean()) for h in range(24)],
            in_attesa_ora=[float(ia[ore == h].mean()) for h in range(24)],
            boarding_n_anno=float(bmask.sum() / anni),
            boarding_ore=float(bo[bmask].mean()) if bmask.any() else 0.0,
            abbandoni_quota=float(ab.mean()),
            quota_tempo_oltre_83=float((pres > 83).mean()),
            accessi_anno=float(len(P) / anni),
            deriva=float(pres[-len(pres)//4:].mean() / pres[:len(pres)//4].mean()),
            accessi_codice={c: float((cod == c).sum() / anni) for c in D.CODICI},
            in_attesa_codice={c: float(ac[:, i].mean()) for i, c in enumerate(D.CODICI)},
            boarding_n_codice={c: float((bmask & (cod == c)).sum() / anni) for c in D.CODICI},
            boarding_ore_codice={c: float(bo[bmask & (cod == c)].mean()) if (bmask & (cod == c)).any() else 0.0
                                 for c in D.CODICI},
            abbandoni_codice={c: per(c, ab) for c in D.CODICI},
        )


def ricoveri_ps_giorno(sc: Scenario) -> float:
    return sum(sc.arrivi_anno[c] * sc.p_ricovero.get(c, 0) for c in sc.arrivi_anno) / 365


def margine_letti(sc: Scenario) -> float:
    """Letti liberi in più al giorno rispetto ai ricoveri (≤0 = coda che cresce senza limite)."""
    return sc.letti_capacita_giorno - ricoveri_ps_giorno(sc) - sc.ricoveri_altri_giorno


def simula(sc: Scenario) -> Risultato:
    r = PS(sc).esegui()
    if margine_letti(sc) <= 0:
        r.deriva = 99.0
    return r


# --------------------------------------------------------------------------- #
# Profilo orario degli arrivi dalle presenze misurate
# --------------------------------------------------------------------------- #
def stima_profilo_arrivi(asl: D.DatiASL, pr: D.Presenze, liscio=2.0):
    """Le presenze L(h) sono la convoluzione degli arrivi λ(h) con la probabilità di essere
    ancora in PS dopo k ore. Conoscendo quest'ultima per codice (dati ASL), ricavo λ(h)
    con minimi quadrati non negativi e un termine di regolarità."""
    from scipy import stats
    K = np.zeros(int(D.T_MAX) + 1)
    for c in D.CODICI:
        mu, s, _ = D.fit_permanenza(asl.permanenza[c], asl.p8[c], asl.p24[c])
        d = stats.lognorm(s=s, scale=math.exp(mu))
        k = np.arange(len(K)) + 0.5
        K += asl.accessi[c] / asl.totale * np.clip(1 - d.cdf(k), 0, None)
    # matrice circolante 24x24 (presenze all'ora h dovute agli arrivi all'ora j)
    A = np.zeros((24, 24))
    for h in range(24):
        for j in range(24):
            lag = (h - j) % 24
            A[h, j] = K[lag::24].sum()
    Dm = np.zeros((24, 24))
    for h in range(24):
        Dm[h, h], Dm[h, (h + 1) % 24] = -1, 1
    y = pr.tot_ora
    scala = y.mean() / A.sum(axis=1).mean()
    M = np.vstack([A * scala, liscio * Dm * scala])
    b = np.concatenate([y, np.zeros(24)])
    f, _ = optimize.nnls(M, b)
    f = f / f.mean()
    return f


# --------------------------------------------------------------------------- #
# Costruzione dello scenario base e calibrazione
# --------------------------------------------------------------------------- #
def scenario_base(cfg, asl, pr, turni=None):
    tm = cfg["tempo_medico_min"]
    turni = turni or cfg["turni_medici"]["scenario"]
    qr = cfg["quota_ricovero"]
    attese = sum(asl.accessi[c] * qr[c] for c in D.CODICI)
    p_ric = {c: min(1.0, qr[c] * asl.boarding_n / attese) for c in D.CODICI}
    # stima iniziale del processo: permanenza - attesa (Little sulle presenze) - boarding - medico
    mus, sig, scala, breve, lm, lq, ls = {}, {}, {}, {}, {}, {}, {}
    for c in D.CODICI:
        att = pr.attesa_codice[c] / (asl.accessi[c] / 8760)
        med = (tm["visita"][c] + tm["rivalutazione"][c]) / 60
        proc = max(0.3, asl.permanenza[c] - att - med - p_ric[c] * asl.boarding_ore)
        mu, s, (m, _, _) = D.fit_permanenza(asl.permanenza[c], asl.p8[c], asl.p24[c])
        mus[c], sig[c], scala[c] = mu, s, 1.0
        q0 = max(0.01, asl.p8[c])
        breve[c] = min(2.0, 0.4 * proc)
        lm[c] = max(1.0, (proc - (1 - q0) * breve[c] * 1.28) / q0 / 1.6)
        lq[c], ls[c] = q0, 0.9
    adm = asl.boarding_n / 365
    return Scenario(
        nome=f"base_{turni}",
        arrivi_anno=dict(asl.accessi),
        profilo_arrivi=list(stima_profilo_arrivi(asl, pr, cfg.get("liscio_arrivi", 6))),
        medici_ora=list(fasce_in_orario(cfg["turni_medici"][turni])),
        t_visita={c: tm["visita"][c] / 60 for c in D.CODICI},
        t_rival={c: tm["rivalutazione"][c] / 60 for c in D.CODICI},
        fattore_medico=1.0,
        processo_mu=mus, processo_sigma=sig, processo_scala=scala,
        lungo_quota=lq, lungo_mediana=lm, lungo_sigma=ls, breve_mediana=breve,
        p_ricovero=p_ric,
        pazienza={int(k): float(v) for k, v in cfg["pazienza_ore"].items()},
        # capacità: domanda + margine che dà l'attesa media di boarding ASL (1/margine)
        letti_capacita_giorno=adm / cfg["letti"]["quota_ps"] + 24 / asl.boarding_ore,
        ricoveri_altri_giorno=adm / cfg["letti"]["quota_ps"] - adm,
        giorni=cfg["simulazione"]["giorni"], warmup=cfg["simulazione"]["warmup_giorni"],
        seed=cfg["simulazione"]["seed"],
        priorita=margini_attesa(asl, pr),
        rival_precedenza=bool(cfg.get("rivalutazione_precedenza", False)),
    )


def margini_attesa(asl, pr):
    """Margine della scadenza per codice = attesa misurata (Little sulle presenze in attesa)."""
    m = {c: pr.attesa_codice[c] / (asl.accessi[c] / 8760) for c in D.CODICI}
    m[1] = -1e6
    return m


def bersagli(asl, pr):
    """Valori che il modello deve riprodurre. Le presenze misurate (autunno 2026) sono
    riportate al carico 2025 in proporzione (Little ASL / media misurata)."""
    L_asl = sum(asl.ore_paziente.values()) / 8760
    k = L_asl / pr.media
    return dict(
        permanenza_codice=asl.permanenza,
        in_attesa=sum(pr.attesa_codice.values()) * k,
        boarding_ore=asl.boarding_ore,
        boarding_n=asl.boarding_n,
        abbandoni_quota=asl.abbandoni / asl.totale,
        presenti=L_asl,
        presenti_ora=list(pr.tot_ora * k),
        in_attesa_ora=list(pr.attesa_ora * k),
        # per codice
        p24_codice=asl.p24,
        p8_codice=asl.p8,
        attesa_codice={c: pr.attesa_codice[c] / (asl.accessi[c] / 8760) for c in D.CODICI},
        presenti_codice={c: (pr.attesa_codice[c] + pr.tratt_codice[c]) * k for c in D.CODICI},
    )


def _bisezione(f, lo, hi, passi=9):
    """Trova x in [lo, hi] con f(x) ≈ 0, f crescente."""
    for _ in range(passi):
        mid = math.sqrt(lo * hi)
        if f(mid) > 0:
            hi = mid
        else:
            lo = mid
    return math.sqrt(lo * hi)


def calibra(sc: Scenario, tgt: dict, giri=3, giorni=120, verbose=True, solo_rifinitura=False,
            solo_permanenze=False):
    """Calibrazione a passi separati (il sistema medici è vicino alla saturazione: un
    aggiornamento congiunto oscilla). Ogni passo regola un parametro su un bersaglio."""
    sc = copy.deepcopy(sc)
    full_giorni = sc.giorni
    sc.giorni = giorni
    def run():
        return simula(sc)

    def passata_permanenze(iterazioni, con_sigma):
        """scala del processo -> permanenza ASL per codice; sigma -> quota oltre 24h (codici 1-3)."""
        for _ in range(iterazioni):
            r = run()
            for c in D.CODICI:
                # quota del percorso lungo -> quota oltre 8 ore
                p8t, p8s = tgt["p8_codice"][c], max(r.p8_codice[c], 1e-3)
                sc.lungo_quota[c] = float(np.clip(sc.lungo_quota[c] * (p8t / p8s) ** 0.7, 0.003, 0.95))
                # dispersione del percorso lungo -> quota oltre 24 ore
                p24t, p24s = tgt["p24_codice"][c], r.p24_codice[c]
                if con_sigma and p24s > 0.002:
                    sc.lungo_sigma[c] = float(np.clip(sc.lungo_sigma[c] * (p24t / p24s) ** 0.3, 0.25, 2.0))
                # durata del percorso lungo -> permanenza media
                rap = tgt["permanenza_codice"][c] / r.permanenza_codice[c]
                sc.lungo_mediana[c] = float(np.clip(sc.lungo_mediana[c] * rap ** 1.2, 0.5, 80.0))
            rb = tgt["boarding_n"] / max(r.boarding_n_anno, 1)
            sc.p_ricovero = {c: min(1.0, p * rb) for c, p in sc.p_ricovero.items()}
            allinea_letti()

    def allinea_letti():
        """capacità dei letti tale che l'attesa media di boarding sia quella ASL (1/margine)."""
        sc.letti_capacita_giorno = ricoveri_ps_giorno(sc) + sc.ricoveri_altri_giorno + 24 / tgt["boarding_ore"]

    def tara_medici():
        """tempo medico -> persone in attesa; pazienza -> abbandoni (annidati)."""
        paz0 = dict(sc.pazienza)
        def f_med(k):
            sc.fattore_medico = k
            def f_paz(a):
                sc.pazienza = {c: v * a for c, v in paz0.items()}
                return tgt["abbandoni_quota"] - run().abbandoni_quota
            a = _bisezione(f_paz, 0.05, 20.0, passi=6)
            sc.pazienza = {c: v * a for c, v in paz0.items()}
            return run().in_attesa - tgt["in_attesa"]
        sc.fattore_medico = _bisezione(f_med, 0.3, 3.0, passi=8)
        f_med(sc.fattore_medico)

    if solo_rifinitura:
        allinea_letti()
        for _ in range(0 if solo_permanenze else 2):
            r = run()
            for c in (2, 3, 4, 5):
                sc.priorita[c] = float(max(-3.0, sc.priorita[c] + 0.5 * (tgt["attesa_codice"][c] - r.attesa_visita_codice[c])))
            tara_medici()
        giri = 0

    for g in range(giri):
        # 1) per codice: permanenza media e quota oltre 24 ore (dati ASL)
        passata_permanenze(4, con_sigma=True)

        # 2) letti: margine analitico = 1 / attesa media di boarding ASL
        allinea_letti()

        # 3) margini della scadenza per codice -> attesa della visita misurata per codice
        if g > 0:
            r = run()
            for c in (2, 3, 4, 5):
                sc.priorita[c] = float(max(-3.0, sc.priorita[c] + 0.5 * (tgt["attesa_codice"][c] - r.attesa_visita_codice[c])))

        # 4) tempo medico -> persone in attesa; 5) pazienza -> abbandoni (annidati)
        paz0 = dict(sc.pazienza)
        def f_med(k):
            sc.fattore_medico = k
            def f_paz(a):
                sc.pazienza = {c: v * a for c, v in paz0.items()}
                return tgt["abbandoni_quota"] - run().abbandoni_quota  # più pazienza -> meno abbandoni
            a = _bisezione(f_paz, 0.05, 20.0, passi=6)
            sc.pazienza = {c: v * a for c, v in paz0.items()}
            return run().in_attesa - tgt["in_attesa"]
        sc.fattore_medico = _bisezione(f_med, 0.3, 3.0, passi=8)
        f_med(sc.fattore_medico)

        r = run()
        if verbose:
            e24 = max(abs(r.p24_codice[c] - tgt["p24_codice"][c]) for c in D.CODICI)
            e8 = max(abs(r.p8_codice[c] - tgt["p8_codice"][c]) for c in D.CODICI)
            print(f"  giro {g}: >8h err max {e8:.1%}", end="")
            eat = max(abs(r.attesa_visita_codice[c] - tgt["attesa_codice"][c]) for c in D.CODICI) * 60
            err = max(abs(r.permanenza_codice[c] / tgt["permanenza_codice"][c] - 1) for c in D.CODICI)
            print(f"  giro {g}: >24h err max {e24:.1%}, attesa codice err max {eat:.0f}′  "
                  f"in attesa {r.in_attesa:5.1f}/{tgt['in_attesa']:.1f}  "
                  f"boarding {r.boarding_ore:5.1f}/{tgt['boarding_ore']:.1f}h  "
                  f"abbandoni {r.abbandoni_quota:.1%}/{tgt['abbandoni_quota']:.1%}  "
                  f"perm. err max {err:.0%}  [f.med {sc.fattore_medico:.2f}, margine letti/g {margine_letti(sc):.2f}]", flush=True)

    # passata finale: medici e attese ora sono fissati, riallineo le permanenze per codice
    passata_permanenze(5 if solo_permanenze else 3, con_sigma=False)
    if verbose:
        r = run()
        err = max(abs(r.permanenza_codice[c] / tgt["permanenza_codice"][c] - 1) for c in D.CODICI)
        print(f"  finale: perm. err max {err:.0%}, in attesa {r.in_attesa:.1f}/{tgt['in_attesa']:.1f}", flush=True)
    sc.giorni = full_giorni
    return sc


def _puro(x):
    if isinstance(x, dict):
        return {k: _puro(v) for k, v in x.items()}
    if isinstance(x, (list, tuple, np.ndarray)):
        return [_puro(v) for v in x]
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, np.floating):
        return float(x)
    return x


def salva_scenario(sc, path):
    with open(path, "w") as f:
        yaml.safe_dump(_puro(asdict(sc)), f, allow_unicode=True, sort_keys=False)


def carica_scenario(path):
    with open(path) as f:
        d = yaml.safe_load(f)
    for k in ("arrivi_anno", "t_visita", "t_rival", "processo_mu", "processo_sigma", "processo_scala",
              "p_ricovero", "pazienza", "priorita", "lungo_quota", "lungo_mediana", "lungo_sigma", "breve_mediana"):
        if k in d:
            d[k] = {int(c): v for c, v in (d[k] or {}).items()}
    d["ft_codici"] = tuple(d.get("ft_codici", ()))
    return Scenario(**d)


def validazione(r: Risultato, tgt, asl, pr):
    """Confronto simulato / reale. Le curve orarie non sono state usate come bersaglio
    del tempo medico: sono un test indipendente del modello."""
    def corr(a, b):
        return float(np.corrcoef(a, b)[0, 1])
    return dict(
        permanenza=(r.permanenza, sum(asl.ore_paziente.values()) / asl.totale),
        permanenza_codice={c: (r.permanenza_codice[c], asl.permanenza[c]) for c in D.CODICI},
        p8_codice={c: (r.p8_codice[c], asl.p8[c]) for c in D.CODICI},
        p24_codice={c: (r.p24_codice[c], asl.p24[c]) for c in D.CODICI},
        attesa_codice={c: (r.attesa_visita_codice[c], pr.attesa_codice[c] / (asl.accessi[c] / 8760)) for c in D.CODICI},
        presenti_codice={c: (r.presenti_codice[c], tgt["presenti_codice"][c]) for c in D.CODICI},
        in_attesa=(r.in_attesa, tgt["in_attesa"]),
        presenti=(r.presenti, tgt["presenti"]),
        boarding_ore=(r.boarding_ore, tgt["boarding_ore"]),
        boarding_n=(r.boarding_n_anno, tgt["boarding_n"]),
        abbandoni=(r.abbandoni_quota, tgt["abbandoni_quota"]),
        corr_presenti_ora=corr(r.presenti_ora, tgt["presenti_ora"]),
        corr_attesa_ora=corr(r.in_attesa_ora, tgt["in_attesa_ora"]),
        errore_attesa_ora=float(np.mean(np.abs(np.array(r.in_attesa_ora) - np.array(tgt["in_attesa_ora"])))),
    )


if __name__ == "__main__":
    import json, sys, time
    OUT = QUI / "output"
    OUT.mkdir(exist_ok=True)
    cfg = carica_config()
    asl, pr = D.carica_asl(cfg["anno_asl"]), D.carica_presenze()
    tgt = bersagli(asl, pr)
    turni = sys.argv[1] if len(sys.argv) > 1 else cfg["turni_medici"]["scenario"]
    if len(sys.argv) > 2:
        cfg["rivalutazione_precedenza"] = "precedenza" in sys.argv[2:]
    var = turni + ("_rivprec" if cfg.get("rivalutazione_precedenza") else "")
    t = time.time()
    print(f"Calibrazione turni {turni} (presenze {pr.inizio[:10]} → {pr.fine[:10]})")
    if "--rifinisci" in sys.argv:
        sc = calibra(carica_scenario(OUT / f"scenario_{var}.yaml"), tgt, solo_rifinitura=True,
                     solo_permanenze="--solo-permanenze" in sys.argv)
    else:
        sc = calibra(scenario_base(cfg, asl, pr, turni), tgt)
    salva_scenario(sc, OUT / f"scenario_{var}.yaml")
    r = simula(sc)
    v = validazione(r, tgt, asl, pr)
    v["simulati"] = dict(presenti_ora=r.presenti_ora, in_attesa_ora=r.in_attesa_ora)
    v["reali"] = dict(presenti_ora=tgt["presenti_ora"], in_attesa_ora=tgt["in_attesa_ora"])
    with open(OUT / f"validazione_{var}.json", "w") as f:
        json.dump(_puro(v), f, indent=1)
    print(f"fatto in {time.time()-t:.0f}s")
    for k in ("permanenza", "in_attesa", "presenti", "boarding_ore", "boarding_n", "abbandoni",
              "corr_presenti_ora", "corr_attesa_ora", "errore_attesa_ora"):
        print(f"  {k}: {v[k]}")
    for k in ("permanenza_codice", "attesa_codice", "p24_codice"):
        print(f"  {k}: " + "  ".join(f"{c}: {a:.2f}/{b:.2f}" for c, (a, b) in v[k].items()))
