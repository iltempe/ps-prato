"""Server locale del gemello digitale PS Santo Stefano.

    cd gemello && .venv/bin/python app.py      ->  http://localhost:8765

Solo libreria standard (http.server) + il modello. Nessun dato esce dal computer: il server
legge soltanto il dato pubblico di pspratolive.it e i file del repo.

API (JSON):
  GET  /api/config              parametri di partenza per l'interfaccia
  GET  /api/stato               ultima rilevazione live + ultime 24 h osservate
  POST /api/prevedi             {parametri} -> forchetta prossime ore (base e scenario)
  POST /api/regime              {parametri} -> indicatori annui simulati (base e scenario)
  GET  /api/storico             serie ASL 2020-2025
  POST /api/job/<tipo>          ottimizza | backtest | calibra | validazione_storica -> {id}
  GET  /api/job/<id>            stato/progresso/risultato
"""
from __future__ import annotations

import copy
import json
import sys
import threading
import time
import traceback
import uuid
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timedelta
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

QUI = Path(__file__).resolve().parent
sys.path.insert(0, str(QUI / "modello"))

import numpy as np  # noqa: E402

import dati as D  # noqa: E402
import gemello as G  # noqa: E402
import ottimizza as O  # noqa: E402
import simulazione as S  # noqa: E402
import storico as ST  # noqa: E402
from pagine import pagina_markdown  # noqa: E402

OUT = QUI / "output"
LIVE_FILE = OUT / "live_storico.json"
POOL: ProcessPoolExecutor | None = None
LOCK = threading.Lock()


# --------------------------------------------------------------------------- #
# Stato condiviso
# --------------------------------------------------------------------------- #
class Stato:
    cfg = None
    asl = None
    pr = None
    serie = None          # osservato: ts -> {"attesa", "tratt"}
    live = None           # ultima rilevazione live
    live_errore = None
    live_letto = None
    live_extra = {}       # rilevazioni live raccolte dal server (oltre al CSV locale)
    base_cache = {}       # (turni, variante) -> Scenario calibrato


def ricarica_dati():
    Stato.cfg = S.carica_config()
    Stato.asl = D.carica_asl(Stato.cfg["anno_asl"])
    Stato.pr = D.carica_presenze()
    if LIVE_FILE.exists():
        Stato.live_extra = json.loads(LIVE_FILE.read_text())
        for v in Stato.live_extra.values():
            for k in ("attesa", "tratt"):
                v[k] = {int(c): n for c, n in v[k].items()}
    Stato.serie = G.storico_osservato(extra=Stato.live_extra)


def aggiorna_live():
    g = Stato.cfg["gemello"]
    while True:
        try:
            st = G.stato_live(g["url_live"])
            Stato.live, Stato.live_errore = st, None
            Stato.live_letto = datetime.now().astimezone().isoformat(timespec="seconds")
            if st["ts"] not in Stato.serie:
                v = {"attesa": st["attesa"], "tratt": st["tratt"]}
                with LOCK:
                    Stato.live_extra[st["ts"]] = v
                    Stato.serie[st["ts"]] = v
                    Stato.serie = dict(sorted(Stato.serie.items()))
                    LIVE_FILE.write_text(json.dumps(Stato.live_extra))
        except Exception as e:  # rete assente, sito giù: si riprova al giro dopo
            Stato.live_errore = f"{type(e).__name__}: {e}"
        time.sleep(60 * g["aggiorna_live_minuti"])


def ultimo_stato():
    """Live se disponibile, altrimenti l'ultima riga dei dati locali."""
    if Stato.live:
        return Stato.live
    ts = list(Stato.serie)[-1]
    return dict(ts=ts, fonte="data/presenze.csv", **Stato.serie[ts])


# --------------------------------------------------------------------------- #
# Parametri dell'interfaccia -> scenario
# --------------------------------------------------------------------------- #
FASCE = ["08-14", "14-20", "20-02", "02-08"]


def scenario_calibrato(turni, variante):
    key = (turni, variante)
    if key not in Stato.base_cache:
        nome = f"scenario_{turni}{'_' + variante if variante else ''}.yaml"
        path = OUT / nome
        if not path.exists():
            raise FileNotFoundError(f"scenario non calibrato: {nome}. Lancia la calibrazione dalla scheda Modello.")
        Stato.base_cache[key] = S.carica_scenario(path)
    return Stato.base_cache[key]


def costruisci(p: dict, base_only=False):
    """Restituisce (scenario_base, scenario_modificato)."""
    turni = p.get("turni", Stato.cfg["turni_medici"]["scenario"])
    prec = p.get("rivalutazione_precedenza", Stato.cfg.get("rivalutazione_precedenza", False))
    variante = "rivprec" if prec else ""
    base = scenario_calibrato(turni, variante)
    sc = copy.deepcopy(base)
    if base_only:
        return base, sc
    leve = {l["id"]: l for l in O.carica_leve()}
    # medici per fascia (valori assoluti)
    if p.get("medici"):
        sc.medici_ora = [int(x) for x in S.fasce_in_orario({f: int(p["medici"][f]) for f in FASCE})]
    sc.fattore_medico *= float(p.get("tempo_medico", 1.0))
    # carico: moltiplicatore + anni di crescita per codice (storico ASL)
    car = float(p.get("carico", 1.0))
    anni = float(p.get("anni_avanti", 0))
    g = O.crescita_annua(Stato.asl, Stato.cfg)
    sc.arrivi_anno = {c: v * car * (1 + g[c]) ** anni for c, v in sc.arrivi_anno.items()}
    # parametri per codice di triage
    for c in D.CODICI:
        q = (p.get("per_codice") or {}).get(str(c)) or (p.get("per_codice") or {}).get(c) or {}
        sc.arrivi_anno[c] *= float(q.get("accessi", 1.0)) * (1 - float(q.get("fuori", 0.0)))
        sc.processo_scala[c] *= 1 - float(q.get("processo", 0.0))
        if "ricovero" in q:
            sc.p_ricovero[c] = min(1.0, sc.p_ricovero[c] * float(q["ricovero"]))
    # letti
    sc.letti_capacita_giorno += float(p.get("letti_extra", 0)) / float(p.get("degenza_giorni", 8))
    sc.letti_capacita_giorno /= 1 - float(p.get("riduzione_degenza", 0))
    if p.get("letti_seguono_ricoveri") and anni:
        sc.letti_capacita_giorno += S.ricoveri_ps_giorno(sc) - S.ricoveri_ps_giorno(base)
    sc.pazienza = {c: v * float(p.get("pazienza", 1.0)) for c, v in sc.pazienza.items()}
    for lid in p.get("leve", []):
        if lid in leve:
            sc = O.applica(sc, leve[lid])
    sc.nome = "scenario"
    return base, sc


def costo_annuo(p):
    """Costo indicativo dei cambiamenti rispetto alla base (stessi costi unitari di leve.yaml)."""
    leve = {l["id"]: l for l in O.carica_leve()}
    turni = p.get("turni", Stato.cfg["turni_medici"]["scenario"])
    base_m = Stato.cfg["turni_medici"][turni]
    costo_medico_fascia = leve["medico_20_02"]["costo_annuo"]
    voci = []
    for f in FASCE:
        d = int(p.get("medici", {}).get(f, base_m[f])) - int(base_m[f])
        if d:
            voci.append((f"{d:+d} medici {f}", d * costo_medico_fascia))
    le = float(p.get("letti_extra", 0))
    if le:
        voci.append((f"{le:+.0f} letti", le * 365 * 600))
    for lid in p.get("leve", []):
        if lid in leve:
            voci.append((leve[lid]["nome"], leve[lid]["costo_annuo"]))
    return dict(voci=voci, totale=sum(v for _, v in voci))


# --------------------------------------------------------------------------- #
# Calcoli
# --------------------------------------------------------------------------- #
def correzione(base):
    g = Stato.cfg["gemello"]["analoghi"]
    lib = G.libreria_analoghi(base, g["giorni"], g["repliche"], POOL)
    return (G.profilo_reale(Stato.serie), G.profilo_modello(lib)) if g.get("correzione_profilo", True) else None


def prevedi(p):
    g = Stato.cfg["gemello"]
    a = g["analoghi"]
    base, sc = costruisci(p)
    st = ultimo_stato()
    if p.get("stato"):               # stato inserito a mano dall'interfaccia
        st = dict(st, **p["stato"])
    t = datetime.fromisoformat(st["ts"])
    ora = t.hour + t.minute / 60
    oriz = float(p.get("orizzonte", g["orizzonte_ore"]))
    corr = correzione(base)
    kw = dict(k=a["k"], tau=a["tau"], finestra_ore=a["finestra_ore"], allarga=a["allarga"],
              percentili=tuple(g["percentili"]), correzione=corr)
    out = {}
    for nome, s in (("base", base), ("scenario", sc)):
        lib = G.libreria_analoghi(s, a["giorni"], a["repliche"], POOL)
        out[nome] = G.prevedi_analoghi(lib, st, ora, oriz, **kw)
    out["inizio"] = st["ts"]
    out["ore_orologio"] = [(t + timedelta(hours=h)).isoformat(timespec="minutes") for h in out["base"]["ore"]]
    out["modificato"] = G.chiave_scenario(base) != G.chiave_scenario(sc)
    return out


CAMPI_CODICE = ("permanenza_codice", "attesa_visita_codice", "p8_codice", "p24_codice", "presenti_codice",
                "accessi_codice", "in_attesa_codice", "boarding_n_codice", "boarding_ore_codice", "abbandoni_codice")


def _riassunto(r):
    return dict(**{k: getattr(r, k) for k in CAMPI_CODICE},
        permanenza=r.permanenza, attesa_visita=r.attesa_visita, p8=r.p8, p24=r.p24,
        presenti=r.presenti, in_attesa=r.in_attesa, boarding_ore=r.boarding_ore,
        boarding_n=r.boarding_n_anno, abbandoni=r.abbandoni_quota,
        oltre_83=r.quota_tempo_oltre_83, accessi=r.accessi_anno, stabile=r.stabile,
        presenti_ora=r.presenti_ora,
        in_attesa_ora=r.in_attesa_ora,
    )


_REGIME = {}


def regime(p):
    g = Stato.cfg["gemello"]["regime"]
    base, sc = costruisci(p)
    res = {}
    for nome, s in (("base", base), ("scenario", sc)):
        key = (G.chiave_scenario(s), g["giorni"], g["repliche"])
        if key not in _REGIME:
            s2 = copy.deepcopy(s)
            s2.giorni = g["giorni"]
            _REGIME[key] = _riassunto(O.valuta([s2], POOL, g["repliche"])[0])
        res[nome] = _REGIME[key]
    t = S.bersagli(Stato.asl, Stato.pr)
    a = Stato.asl
    res["reale"] = dict(permanenza=sum(a.ore_paziente.values()) / a.totale,
                        permanenza_codice=a.permanenza, p8_codice=a.p8, p24_codice=a.p24,
                        accessi_codice=a.accessi,
                        attesa_visita_codice=t["attesa_codice"], presenti_codice=t["presenti_codice"],
                        presenti_ora=list(Stato.pr.tot_ora), in_attesa_ora=list(Stato.pr.attesa_ora),
                        presenti_ora_2025=t["presenti_ora"])
    res["costo"] = costo_annuo(p)
    res["margine_letti_giorno"] = S.margine_letti(sc)
    return res


# --------------------------------------------------------------------------- #
# Lavori lunghi
# --------------------------------------------------------------------------- #
JOBS = {}


def nuovo_job(tipo, p):
    jid = uuid.uuid4().hex[:8]
    JOBS[jid] = dict(id=jid, tipo=tipo, stato="in corso", progresso=0.0, log=[], risultato=None,
                     inizio=time.time())
    threading.Thread(target=_esegui_job, args=(jid, tipo, p), daemon=True).start()
    return jid


def _esegui_job(jid, tipo, p):
    J = JOBS[jid]
    def log(s):
        J["log"].append(s)
    def prog(x, s=None):
        J["progresso"] = x
        if s:
            J["messaggio"] = s
    try:
        if tipo == "ottimizza":
            J["risultato"] = job_ottimizza(p, log, prog)
        elif tipo == "backtest":
            J["risultato"] = job_backtest(p, log, prog)
        elif tipo == "calibra":
            J["risultato"] = job_calibra(p, log, prog)
        elif tipo == "validazione_storica":
            J["risultato"] = job_storica(p, log, prog)
        else:
            raise ValueError(tipo)
        J["stato"] = "fatto"
    except Exception as e:
        J["stato"] = "errore"
        J["errore"] = f"{type(e).__name__}: {e}"
        J["log"].append(traceback.format_exc())
    J["durata"] = time.time() - J["inizio"]


def job_ottimizza(p, log, prog):
    _, sc = costruisci(p)
    target = float(p.get("target", Stato.cfg["target_riduzione"]))
    metrica = p.get("metrica", Stato.cfg["metrica_target"])
    if metrica not in O.METRICHE:
        raise ValueError(f"metrica sconosciuta: {metrica}")
    O.REPLICHE = Stato.cfg["simulazione"].get("repliche", 4)
    leve = O.carica_leve()
    prog(0.05, "simulazione di partenza")
    base_r = O.valuta([sc], POOL)[0]
    m0 = O.metrica(base_r, metrica)
    prog(0.1, "leve singole")
    singole = O.valuta([O.applica(sc, l) for l in leve], POOL)
    tab = []
    for l, r in zip(leve, singole):
        gpe = 1 - O.metrica(r, metrica) / m0
        tab.append(dict(nome=l["nome"], id=l["id"], effetto=gpe, costo=l["costo_annuo"],
                        attesa=r.attesa_visita, oltre_83=r.quota_tempo_oltre_83))
    tab.sort(key=lambda x: -(x["effetto"] / x["costo"]))
    prog(0.3, "ricerca del mix")
    passi_n = [0]
    def log2(s):
        log(s)
        passi_n[0] += 1
        prog(min(0.95, 0.3 + 0.08 * passi_n[0]), s.strip())
    scelte, passi, _ = O.greedy(sc, base_r, leve, target, metrica, POOL, log2)
    fin = passi[-1]["risultato"] if passi else base_r
    return dict(
        target=target, metrica=metrica, metrica_nome=O.METRICHE[metrica],
        valore_partenza=m0, valore_finale=O.metrica(fin, metrica),
        partenza=_riassunto(base_r), finale=_riassunto(fin),
        singole=tab,
        passi=[dict(leva=x["leva"], guadagno=x["guadagno"], cumulato=x["cumulato"], costo=x["costo"]) for x in passi],
        raggiunto=1 - O.metrica(fin, metrica) / m0,
    )


def job_backtest(p, log, prog):
    g = Stato.cfg["gemello"]
    base, sc = costruisci(p)
    a = dict(g["analoghi"])
    b = G.backtest(sc, giorni=int(p.get("giorni", g["backtest"]["giorni"])),
                   ogni_ore=float(p.get("ogni_ore", g["backtest"]["ogni_ore"])),
                   orizzonte=float(p.get("orizzonte", g["orizzonte_ore"])),
                   pool=POOL, progresso=prog, extra=Stato.live_extra, opz_analoghi=a)
    return b


def job_calibra(p, log, prog):
    turni = p.get("turni", "A")
    prec = bool(p.get("rivalutazione_precedenza", Stato.cfg.get("rivalutazione_precedenza", False)))
    anno = int(p.get("anno", Stato.cfg["anno_asl"]))
    cfg = copy.deepcopy(Stato.cfg)
    cfg["rivalutazione_precedenza"] = prec
    cfg["anno_asl"] = anno
    asl = D.carica_asl(anno)
    tgt = S.bersagli(asl, Stato.pr)
    prog(0.05, f"calibrazione turni {turni}, anno {anno}")
    import io, contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        sc = S.calibra(S.scenario_base(cfg, asl, Stato.pr, turni), tgt)
    log(buf.getvalue())
    var = turni + ("_rivprec" if prec else "")
    if anno != Stato.cfg["anno_asl"]:
        var += f"_{anno}"
    S.salva_scenario(sc, OUT / f"scenario_{var}.yaml")
    prog(0.9, "validazione")
    r = S.simula(sc)
    v = S.validazione(r, tgt, asl, Stato.pr)
    (OUT / f"validazione_{var}.json").write_text(json.dumps(S._puro(v), indent=1))
    Stato.base_cache.clear()
    return dict(file=f"scenario_{var}.yaml", validazione=S._puro(v))


def job_storica(p, log, prog):
    base, _ = costruisci(p, base_only=True)
    g = Stato.cfg["gemello"]["regime"]
    s2 = copy.deepcopy(base)
    s2.giorni = g["giorni"]
    prog(0.1, "simulazione degli anni 2020-2025 con gli accessi di ciascun anno")
    righe = ST.validazione_storica(s2, valuta=lambda lst: O.valuta(lst, POOL, g["repliche"]))
    return dict(righe=S._puro(righe))


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #
def _json_ok(o):
    def conv(x):
        if isinstance(x, (np.floating,)):
            return float(x)
        if isinstance(x, (np.integer,)):
            return int(x)
        if isinstance(x, np.ndarray):
            return x.tolist()
        raise TypeError(type(x))
    return json.dumps(o, default=conv, allow_nan=False).encode()


def _nan_none(o):
    if isinstance(o, float) and (o != o or o in (float("inf"), float("-inf"))):
        return None
    if isinstance(o, dict):
        return {str(k): _nan_none(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_nan_none(v) for v in o]
    return o


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(QUI / "ui"), **kw)

    def translate_path(self, path):
        """In locale: /assets/* e /favicon.svg dalla radice del repo, /gemello/ui/* = ui/*."""
        p = path.split("?", 1)[0].split("#", 1)[0]
        if p.startswith("/assets/") or p in ("/favicon.svg", "/privacy.html"):
            return str(D.ROOT / p.lstrip("/"))
        if p.startswith("/gemello/ui/"):
            path = "/" + p[len("/gemello/ui/"):]
        return super().translate_path(path)

    def log_message(self, fmt, *args):
        if "/api/job/" not in str(args[0] if args else ""):
            sys.stderr.write("%s\n" % (fmt % args))

    def _send(self, obj, code=200):
        body = _json_ok(_nan_none(S._puro(obj)))
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        try:
            if self.path == "/api/config":
                return self._send(api_config())
            if self.path == "/api/stato":
                return self._send(api_stato())
            if self.path == "/api/storico":
                return self._send(dict(serie=ST.serie(), crescita=ST.crescita_per_codice(),
                                       crescita_totale=ST.crescita_totale()))
            if self.path in ("/guida", "/metodo", "/guida.html", "/metodo.html"):
                nome = "GUIDA.md" if "guida" in self.path else "METODO.md"
                html = pagina_markdown((QUI / nome).read_text(encoding="utf-8"), nome,
                                       attivo="guida" if "guida" in self.path else "metodo")
                body = html.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if self.path.startswith("/api/job/"):
                j = JOBS.get(self.path.rsplit("/", 1)[1])
                return self._send(j or {"errore": "job inesistente"}, 200 if j else 404)
        except Exception as e:
            traceback.print_exc()
            return self._send({"errore": f"{type(e).__name__}: {e}"}, 500)
        return super().do_GET()

    def do_POST(self):
        try:
            p = self._body()
            if self.path == "/api/prevedi":
                return self._send(prevedi(p))
            if self.path == "/api/regime":
                return self._send(regime(p))
            if self.path.startswith("/api/job/"):
                return self._send({"id": nuovo_job(self.path.rsplit("/", 1)[1], p)})
            if self.path == "/api/ricarica":
                ricarica_dati()
                Stato.base_cache.clear()
                return self._send({"ok": True, "presenze_fino_a": list(Stato.serie)[-1]})
        except FileNotFoundError as e:
            return self._send({"errore": str(e)}, 409)
        except Exception as e:
            traceback.print_exc()
            return self._send({"errore": f"{type(e).__name__}: {e}"}, 500)
        self._send({"errore": "endpoint sconosciuto"}, 404)



def api_config():
    cfg = Stato.cfg
    leve = O.carica_leve()
    disponibili = sorted(p.stem.replace("scenario_", "") for p in OUT.glob("scenario_*.yaml"))
    return dict(
        config=cfg, leve=leve, fasce=FASCE, scenari_calibrati=disponibili, metriche=O.METRICHE,
        crescita=O.crescita_annua(Stato.asl, cfg),
        anni_asl=D.anni_disponibili(),
        presenze=dict(inizio=Stato.pr.inizio, fine=Stato.pr.fine, n=Stato.pr.n),
        asl=dict(anno=Stato.asl.anno, accessi=Stato.asl.accessi, permanenza=Stato.asl.permanenza,
                 boarding_n=Stato.asl.boarding_n, boarding_ore=Stato.asl.boarding_ore),
    )


def api_stato():
    st = ultimo_stato()
    fine = datetime.fromisoformat(st["ts"])
    serie = [(ts, v) for ts, v in Stato.serie.items()
             if fine - timedelta(hours=24) <= datetime.fromisoformat(ts) <= fine]
    return dict(
        ultimo=st, live_errore=Stato.live_errore, live_letto=Stato.live_letto,
        storia=dict(ts=[t for t, _ in serie],
                    presenti=[sum(v["attesa"].values()) + sum(v["tratt"].values()) for _, v in serie],
                    in_attesa=[sum(v["attesa"].values()) for _, v in serie],
                    per_codice={c: dict(presenti=[v["attesa"][c] + v["tratt"][c] for _, v in serie],
                                        in_attesa=[v["attesa"][c] for _, v in serie]) for c in D.CODICI}),
    )


def main():
    global POOL
    ricarica_dati()
    POOL = ProcessPoolExecutor(Stato.cfg["simulazione"]["processi"])
    threading.Thread(target=aggiorna_live, daemon=True).start()
    porta = Stato.cfg["gemello"]["porta"]
    srv = ThreadingHTTPServer(("127.0.0.1", porta), Handler)
    print(f"Gemello digitale PS Santo Stefano: http://localhost:{porta}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        POOL.shutdown(cancel_futures=True)


if __name__ == "__main__":
    main()
