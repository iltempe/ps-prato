"""Su cosa investire e quando.

1. Ogni leva da sola: effetto simulato e costo per punto percentuale di riduzione.
2. Mix: ricerca "greedy" sulla simulazione (a ogni passo aggiunge la leva con il miglior
   rapporto riduzione/costo dato quello che c'è già) fino all'obiettivo.
   La simulazione tiene conto delle interazioni (es. più medici servono a poco se
   i pazienti restano bloccati a valle).
3. Quando, nella giornata: +1 medico in ciascuna fascia di 2 ore.
4. Quando, negli anni: proiezione con la crescita degli accessi, senza e con il mix.

Uso:  python ottimizza.py [--target 0.30] [--metrica permanenza|attesa] [--turni A|B]
"""
from __future__ import annotations

import argparse
import copy
import json
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import yaml

import dati as D
import simulazione as S
from bilancio import testo as testo_bilancio

QUI = D.GEMELLO
OUT = QUI / "output"


def carica_leve():
    with open(QUI / "leve.yaml") as f:
        return yaml.safe_load(f)["leve"]


def applica(sc: S.Scenario, leva: dict) -> S.Scenario:
    sc = copy.deepcopy(sc)
    t = leva["tipo"]
    if t == "medici":
        sc.medici_ora = list(np.array(sc.medici_ora) + S.fasce_in_orario(leva["fasce"]))
    elif t == "fast_track":
        sc.ft_ora = list(np.array(sc.ft_ora) + S.fasce_in_orario(leva["fasce"]))
        sc.ft_codici = tuple(leva["codici"])
        sc.ft_riduzione_processo = leva.get("riduzione_processo", 0.0)
    elif t == "letti":
        sc.letti_capacita_giorno += leva["letti"] / leva["degenza_media_giorni"]
    elif t == "dimissioni":
        # degenza media più corta del x% = stessi letti che si liberano più spesso
        sc.letti_capacita_giorno /= 1 - leva["riduzione_degenza"]
    elif t == "processo":
        for c in leva["codici"]:
            sc.processo_scala[c] *= 1 - leva["riduzione"]
    elif t == "deflessione":
        for c, q in leva["quota"].items():
            sc.arrivi_anno[int(c)] *= 1 - q
    elif t == "crescita":
        # fattore: numero (uguale per tutti) o dict codice -> fattore
        f = leva["fattore"]
        sc.arrivi_anno = {c: v * (f[c] if isinstance(f, dict) else f) for c, v in sc.arrivi_anno.items()}
    else:
        raise ValueError(t)
    return sc


def applica_tutte(sc, leve):
    for l in leve:
        sc = applica(sc, l)
    return sc


# --------------------------------------------------------------------------- #
# Esecuzione parallela con repliche (semi diversi, media)
# --------------------------------------------------------------------------- #
REPLICHE = 2


def _run(sc):
    return S.simula(sc)


def valuta(scenari: list, pool, repliche=None) -> list:
    rep = repliche or REPLICHE
    jobs = []
    for sc in scenari:
        for k in range(rep):
            s2 = copy.deepcopy(sc)
            s2.seed = sc.seed + 1000 * k
            jobs.append(s2)
    res = list(pool.map(_run, jobs))
    out = []
    for i in range(len(scenari)):
        rr = res[i * rep:(i + 1) * rep]
        out.append(media_risultati(rr))
    return out


def media_risultati(rr):
    m = copy.deepcopy(rr[0])
    for campo in ("permanenza", "p8", "p24", "attesa_visita", "in_attesa", "presenti",
                  "boarding_n_anno", "boarding_ore", "abbandoni_quota", "quota_tempo_oltre_83"):
        setattr(m, campo, float(np.mean([getattr(r, campo) for r in rr])))
    m.presenti_ora = list(np.mean([r.presenti_ora for r in rr], axis=0))
    m.in_attesa_ora = list(np.mean([r.in_attesa_ora for r in rr], axis=0))
    for campo in ("permanenza_codice", "attesa_visita_codice", "p8_codice", "p24_codice", "presenti_codice",
                  "accessi_codice", "in_attesa_codice", "boarding_n_codice", "boarding_ore_codice", "abbandoni_codice"):
        if getattr(rr[0], campo):
            setattr(m, campo, {c: float(np.nanmean([getattr(r, campo)[c] for r in rr])) for c in D.CODICI})
    return m


def n0(x):
    return f"{x:,.0f}".replace(",", ".")


def pc(x, segno=True):
    """Variazione percentuale con segno: riduzione -> '-12%', aumento -> '+5%'."""
    v = -x
    return f"{v:+.1%}" if segno else f"{x:.1%}"


def cella(r, testo):
    return testo if r.stabile else "**instabile** (code in crescita)"


METRICHE = {"permanenza": "permanenza media in PS", "attesa": "attesa della prima visita",
            "presenti": "presenti medi in PS (ore-paziente: affollamento)"}
for _c in D.CODICI:
    METRICHE[f"permanenza_c{_c}"] = f"permanenza media dei codici {_c}"
    METRICHE[f"attesa_c{_c}"] = f"attesa della prima visita dei codici {_c}"


def metrica(r, nome):
    """permanenza | attesa | permanenza_c3 | attesa_c4 ..."""
    if nome == "permanenza":
        return r.permanenza
    if nome == "attesa":
        return r.attesa_visita
    if nome == "presenti":
        return r.presenti
    tipo, c = nome.split("_c")
    return (r.permanenza_codice if tipo == "permanenza" else r.attesa_visita_codice)[int(c)]


def unita(leve):
    """Espande le leve ripetibili in unità (es. +1 medico, +2 medici)."""
    out = []
    for l in leve:
        for k in range(l.get("max_unita", 1)):
            u = dict(l)
            u["uid"] = f"{l['id']}#{k+1}" if l.get("max_unita", 1) > 1 else l["id"]
            u["etichetta"] = l["nome"] + (f" (unità {k+1})" if l.get("max_unita", 1) > 1 else "")
            out.append(u)
    return out


def greedy(base_sc, base_r, leve, target, nome_met, pool, log):
    m0 = metrica(base_r, nome_met)
    scelte, sc_cur, m_cur = [], base_sc, m0
    disponibili = unita(leve)
    passi = []
    while disponibili and (1 - m_cur / m0) < target:
        # le unità successive di una leva diventano disponibili solo dopo la precedente
        candidati = [u for u in disponibili
                     if not u["uid"].endswith(tuple(f"#{k}" for k in range(2, 10)))
                     or any(s["id"] == u["id"] for s in scelte)]
        visti = set()
        candidati = [u for u in candidati if not (u["id"] in visti or visti.add(u["id"]))]
        rs = valuta([applica(sc_cur, u) for u in candidati], pool)
        punteggi = []
        for u, r in zip(candidati, rs):
            guadagno = (m_cur - metrica(r, nome_met)) / m0
            punteggi.append((guadagno / u["costo_annuo"] * 1e6, guadagno, u, r))
        punteggi.sort(key=lambda x: -x[0])
        best = punteggi[0]
        if best[1] <= 0.002:
            log(f"  nessuna leva migliora ancora (miglior guadagno {best[1]:.2%}): mi fermo")
            break
        _, g, u, r = best
        scelte.append(u)
        disponibili.remove(u)
        sc_cur = applica(sc_cur, u)
        m_cur = metrica(r, nome_met)
        passi.append(dict(leva=u["etichetta"], guadagno=g, cumulato=1 - m_cur / m0,
                          costo=u["costo_annuo"], risultato=r))
        log(f"  + {u['etichetta']}: -{g:.1%} (cumulato -{1-m_cur/m0:.1%}), {u['costo_annuo']/1e3:.0f} k€/anno")
    return scelte, passi, sc_cur


def crescita_annua(asl, cfg):
    """Crescita annua degli accessi PER CODICE (dati ASL storici). La crescita 2022-2025 è
    concentrata nei codici 4-5: un tasso unico sovrastimerebbe i ricoveri."""
    import storico
    g = cfg.get("crescita_accessi", "auto")
    if g == "auto":
        p = cfg.get("crescita_periodo", [2022, 2025])
        return storico.crescita_per_codice(p[0], p[1])
    if isinstance(g, dict):
        return {int(c): float(v) for c, v in g.items()}
    return {c: float(g) for c in D.CODICI}


# --------------------------------------------------------------------------- #
def main():
    cfg = S.carica_config()
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=float, default=cfg["target_riduzione"])
    ap.add_argument("--metrica", default=cfg["metrica_target"], choices=list(METRICHE))
    ap.add_argument("--turni", default=cfg["turni_medici"]["scenario"])
    ap.add_argument("--variante", default="rivprec" if cfg.get("rivalutazione_precedenza") else "",
                    help="'rivprec' = rivalutazione con precedenza (default da config.yaml); 'normale' = senza")
    a = ap.parse_args()
    global REPLICHE
    REPLICHE = cfg["simulazione"].get("repliche", REPLICHE)
    if a.variante == "normale":
        a.variante = ""
    var = a.turni + (f"_{a.variante}" if a.variante else "")

    righe_log = []
    def log(s=""):
        print(s, flush=True)
        righe_log.append(s)

    t0 = time.time()
    asl, pr = D.carica_asl(cfg["anno_asl"]), D.carica_presenze()
    path = OUT / f"scenario_{var}.yaml"
    if not path.exists():
        raise SystemExit(f"manca {path}: esegui prima la calibrazione (python simulazione.py {a.turni})")
    base = S.carica_scenario(path)
    with open(OUT / f"validazione_{var}.json") as f:
        val = json.load(f)
    leve = carica_leve()
    g = crescita_annua(asl, cfg)

    with ProcessPoolExecutor(cfg["simulazione"]["processi"]) as pool:
        base_r = valuta([base], pool)[0]
        m0 = metrica(base_r, a.metrica)
        log(f"Base (turni {a.turni}): permanenza {base_r.permanenza:.1f}h, attesa visita "
            f"{base_r.attesa_visita*60:.0f} min, presenti {base_r.presenti:.0f}, "
            f">83 presenti {base_r.quota_tempo_oltre_83:.0%} del tempo")

        # 1. leve singole
        log("\n[1] Leve singole")
        singole = valuta([applica(base, l) for l in leve], pool)
        tab_singole = []
        for l, r in zip(leve, singole):
            gpe = 1 - metrica(r, a.metrica) / m0
            tab_singole.append((l, r, gpe))
            log(f"  {l['nome']}: -{gpe:.1%}")
        tab_singole.sort(key=lambda x: -(x[2] / x[0]["costo_annuo"]))

        # 2. mix
        log(f"\n[2] Mix per -{a.target:.0%} di {a.metrica}")
        scelte, passi, sc_mix = greedy(base, base_r, leve, a.target, a.metrica, pool, log)
        mix_r = passi[-1]["risultato"] if passi else base_r
        raggiunto = 1 - metrica(mix_r, a.metrica) / m0

        # 3. fasce orarie: +1 medico per 2 ore
        log("\n[3] +1 medico per fascia di 2 ore")
        fasce = [f"{h:02d}-{(h+2)%24:02d}" for h in range(0, 24, 2)]
        rf = valuta([applica(base, {"tipo": "medici", "fasce": {f: 1}}) for f in fasce], pool)
        tab_fasce = [(f, 1 - r.attesa_visita / base_r.attesa_visita, 1 - r.permanenza / base_r.permanenza)
                     for f, r in zip(fasce, rf)]

        # 4. anni
        log("\n[4] Proiezione con crescita accessi per codice " +
            ", ".join(f"c{c} {v:+.1%}" for c, v in g.items()))
        anni = list(range(asl.anno + 1, asl.anno + 1 + cfg["anni_proiezione"]))
        fatt = [{c: (1 + g[c]) ** (y - asl.anno) for c in D.CODICI} for y in anni]
        rb = valuta([applica(base, {"tipo": "crescita", "fattore": f}) for f in fatt], pool)
        rm = valuta([applica(sc_mix, {"tipo": "crescita", "fattore": f}) for f in fatt], pool)
        # mix + letti per il PS che crescono come i ricoveri
        rl = []
        for f in fatt:
            s2 = applica(sc_mix, {"tipo": "crescita", "fattore": f})
            # letti che crescono quanto basta a mantenere il margine del 2025
            s2.letti_capacita_giorno += S.ricoveri_ps_giorno(s2) - S.ricoveri_ps_giorno(sc_mix)
            rl.append(s2)
        rl = valuta(rl, pool)
        tab_anni = list(zip(anni, fatt, rb, rm, rl))

    # ---------------------------------------------------------------- report
    R = []
    R.append(f"# Modello PS Santo Stefano: obiettivo -{a.target:.0%} di {a.metrica}\n")
    R.append(f"Dati ASL {asl.anno} (accesso civico prot. 158918/2026) + presenze misurate ogni 15 minuti "
             f"({pr.inizio[:10]} → {pr.fine[:10]}, {pr.n} rilevazioni). Turni medici: lettura {a.turni}{' (rivalutazione con precedenza)' if a.variante else ''}. "
             f"Simulazione: {base.giorni} giorni × {REPLICHE} repliche per scenario.\n")
    R.append("## 1. Dove sta il tempo (bilancio ore-paziente)\n")
    R.append(testo_bilancio(a.target) + "\n")

    R.append("## 2. Il modello riproduce la realtà?\n")
    R.append("| Indicatore | Simulato | Reale |\n|---|---|---|")
    def riga(n, k, fmt):
        s, r = val[k]
        R.append(f"| {n} | {fmt(s)} | {fmt(r)} |")
    riga("Permanenza media", "permanenza", lambda x: f"{x:.1f} h")
    riga("Presenti medi", "presenti", lambda x: f"{x:.0f}")
    riga("Persone in attesa visita", "in_attesa", lambda x: f"{x:.1f}")
    riga("Boarding / anno", "boarding_n", lambda x: f"{x:,.0f}".replace(",", "."))
    riga("Attesa boarding", "boarding_ore", lambda x: f"{x:.1f} h")
    riga("Abbandoni", "abbandoni", lambda x: f"{x:.1%}")
    for c in D.CODICI:
        s, r = val["permanenza_codice"][str(c)]
        s2, r2 = val["p24_codice"][str(c)]
        s3, r3 = val["attesa_codice"][str(c)]
        R.append(f"| Codice {c}: permanenza / >24h / attesa visita | {s:.1f}h / {s2:.0%} / {s3*60:.0f}′ "
                 f"| {r:.1f}h / {r2:.0%} / {r3*60:.0f}′ |")
    R.append(f"\nTest indipendenti (curve orarie non usate per calibrare): correlazione presenti per ora "
             f"**{val['corr_presenti_ora']:.2f}**, persone in attesa per ora **{val['corr_attesa_ora']:.2f}** "
             f"(errore medio {val['errore_attesa_ora']:.1f} persone).\n")

    R.append("## 3. Ogni leva da sola (ordinate per efficienza)\n")
    R.append(f"| Leva | Effetto su {a.metrica} | Costo/anno | Costo per punto % | Attesa visita | Tempo con >83 presenti |")
    R.append("|---|---|---|---|---|---|")
    for l, r, gpe in tab_singole:
        eff = f"{n0(l['costo_annuo']/(gpe*100)/1e3)} k€" if gpe > 0.001 else "—"
        R.append(f"| {l['nome']} | {pc(gpe)} | {n0(l['costo_annuo']/1e3)} k€ | {eff} | "
                 f"{r.attesa_visita*60:.0f}′ | {r.quota_tempo_oltre_83:.0%} |")
    R.append(f"\nBase: permanenza {base_r.permanenza:.1f}h, attesa visita {base_r.attesa_visita*60:.0f}′, "
             f"oltre 83 presenti il {base_r.quota_tempo_oltre_83:.0%} del tempo. "
             f"Rumore statistico tipico: ±1-2 punti.\n")

    R.append(f"## 4. Su cosa investire: mix minimo per -{a.target:.0%}\n")
    if passi:
        R.append("| Ordine | Leva | Guadagno | Cumulato | Costo/anno | Costo cumulato |\n|---|---|---|---|---|---|")
        cum = 0
        for i, p in enumerate(passi, 1):
            cum += p["costo"]
            R.append(f"| {i} | {p['leva']} | {pc(p['guadagno'])} | {pc(p['cumulato'])} | "
                     f"{n0(p['costo']/1e3)} k€ | {cum/1e6:.2f} M€ |")
    esito = "raggiunto" if raggiunto >= a.target - 1e-9 else "NON raggiunto con le leve disponibili"
    R.append(f"\nObiettivo {esito}: {pc(raggiunto)}. Permanenza {base_r.permanenza:.1f}h → {mix_r.permanenza:.1f}h, "
             f"attesa visita {base_r.attesa_visita*60:.0f}′ → {mix_r.attesa_visita*60:.0f}′, "
             f">24h {base_r.p24:.1%} → {mix_r.p24:.1%}, tempo oltre 83 presenti "
             f"{base_r.quota_tempo_oltre_83:.0%} → {mix_r.quota_tempo_oltre_83:.0%}.\n")

    R.append("## 5. Quando, nella giornata: +1 medico per 2 ore\n")
    R.append("| Fascia | Effetto su attesa visita | Effetto su permanenza |\n|---|---|---|")
    for f, da, dp in sorted(tab_fasce, key=lambda x: -x[1]):
        R.append(f"| {f} | {pc(da)} | {pc(dp)} |")
    R.append("")

    R.append("## 6. Quando, negli anni: crescita accessi per codice (media 2022-2025: " +
             ", ".join(f"cod. {c} {v:+.1%}" for c, v in g.items()) + ")\n")
    R.append("| Anno | Accessi | Senza interventi (letti invariati) | Con il mix, letti invariati | Con il mix + letti in proporzione ai ricoveri |")
    R.append("|---|---|---|---|---|")
    for y, f, r1, r2, r3 in tab_anni:
        def t(r):
            return cella(r, f"{r.permanenza:.1f}h (boarding {r.boarding_ore:.0f}h, {pc(1-metrica(r, a.metrica)/m0)})")
        R.append(f"| {y} | {n0(sum(asl.accessi[c]*f[c] for c in D.CODICI))} | {t(r1)} | {t(r2)} | {t(r3)} |")
    R.append("\nTra parentesi: attesa media di boarding e variazione della metrica rispetto al 2025.\n")
    R.append("## Avvertenze\n")
    R.append("- Costi ed effetti delle leve di tipo *processo* e *fast track* sono ipotesi (vedi `leve.yaml`): "
             "il modello dice cosa succede SE l'ipotesi è vera.")
    R.append("- Il boarding ufficiale (ASL) conta solo l'attesa dopo la decisione di ricovero. Parte delle permanenze "
             "lunghe nel 'processo' (OBI, attese di consulenze e posti letto prima della disposizione) potrebbe "
             "essere boarding non dichiarato: in quel caso le leve sui letti valgono più di quanto stimato qui.")
    R.append("- I dati ASL sono medie annue; le presenze misurate coprono solo l'autunno 2026 e "
             "non distinguono giorni feriali/festivi nel modello.")
    R.append(f"\n_Tempo di calcolo: {time.time()-t0:.0f}s._")

    OUT.mkdir(exist_ok=True)
    nome = OUT / f"report_{var}_{a.metrica}_{int(a.target*100)}.md"
    nome.write_text("\n".join(R), encoding="utf-8")
    log(f"\nReport: {nome}")


if __name__ == "__main__":
    main()
