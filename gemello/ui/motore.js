/* Motore di simulazione del PS in JavaScript: porta 1:1 di modello/simulazione.py (classe PS),
   per far girare le simulazioni nel browser di chi visita pspratolive.it.
   Stessa logica, stessi parametri (scenario calibrato esportato da Python).
   Funziona sia nel browser (Web Worker) sia in Node (test di coerenza con Python). */
(function (root) {
  "use strict";
  const CODICI = [1, 2, 3, 4, 5];
  const T_MAX = 120.0;

  /* ---------------- numeri casuali riproducibili ---------------- */
  function rng(seed) {
    let a = (seed >>> 0) || 1;
    const u = () => {                       // mulberry32
      a = (a + 0x6D2B79F5) >>> 0;
      let t = a;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
    let spare = null;
    const normale = () => {
      if (spare !== null) { const s = spare; spare = null; return s; }
      let x, y, r;
      do { x = 2 * u() - 1; y = 2 * u() - 1; r = x * x + y * y; } while (r >= 1 || r === 0);
      const f = Math.sqrt(-2 * Math.log(r) / r);
      spare = y * f; return x * f;
    };
    return {
      u,
      expo: rate => -Math.log(1 - u()) / rate,
      lognormMu: (mu, s) => { for (;;) { const x = Math.exp(mu + s * normale()); if (x < T_MAX) return x; } },
      lognormMedia: function (media, s) { return this.lognormMu(Math.log(media) - s * s / 2, s); },
      scegli: (valori, pesi) => {
        const tot = pesi.reduce((a, b) => a + b, 0);
        let x = u() * tot;
        for (let i = 0; i < valori.length; i++) { x -= pesi[i]; if (x <= 0) return valori[i]; }
        return valori[valori.length - 1];
      },
    };
  }

  /* ---------------- heap binario ---------------- */
  class Heap {
    constructor(less) { this.a = []; this.less = less; }
    get size() { return this.a.length; }
    push(x) {
      const a = this.a; a.push(x);
      let i = a.length - 1;
      while (i > 0) { const p = (i - 1) >> 1; if (!this.less(a[i], a[p])) break; [a[i], a[p]] = [a[p], a[i]]; i = p; }
    }
    pop() {
      const a = this.a, top = a[0], last = a.pop();
      if (a.length) {
        a[0] = last; let i = 0;
        for (;;) {
          const l = 2 * i + 1, r = l + 1; let m = i;
          if (l < a.length && this.less(a[l], a[m])) m = l;
          if (r < a.length && this.less(a[r], a[m])) m = r;
          if (m === i) break;
          [a[i], a[m]] = [a[m], a[i]]; i = m;
        }
      }
      return top;
    }
    peek() { return this.a[0]; }
  }

  /* ---------------- pool di medici con orario per ora del giorno ---------------- */
  class Pool {
    constructor(sim, orario) {
      this.sim = sim; this.orario = orario; this.busy = 0;
      this.q = new Heap((x, y) => x.prio < y.prio || (x.prio === y.prio && x.seq < y.seq));
    }
    cap() { return this.orario[Math.floor(this.sim.t) % 24]; }
    richiedi(req) { this.q.push(req); this.distribuisci(); }
    distribuisci() {
      while (this.busy < this.cap() && this.q.size) {
        const r = this.q.pop();
        if (r.fatto) continue;                 // già servito dall'altro pool o abbandonato
        r.fatto = true; this.busy++;
        r.concesso(this);
      }
    }
    rilascia() { this.busy--; this.distribuisci(); }
  }

  /* ---------------- simulazione ---------------- */
  function simula(sc, opz = {}) {
    const R = rng(sc.seed || 42);
    const ev = new Heap((x, y) => x.t < y.t || (x.t === y.t && x.seq < y.seq));
    let seq = 0;
    const sim = { t: opz.t0 || 0 };
    const at = (t, fn) => ev.push({ t, seq: seq++, fn });

    const tInizio = opz.t0 != null ? opz.t0 : sc.warmup * 24;
    const tFine = tInizio + sc.giorni * 24;
    const medici = new Pool(sim, sc.medici_ora);
    const ft = sc.ft_ora && sc.ft_ora.some(x => x > 0) ? new Pool(sim, sc.ft_ora) : null;
    const ftCodici = new Set((sc.ft_codici || []).map(Number));
    const attesa = { 1: 0, 2: 0, 3: 0, 4: 0, 5: 0 }, tratt = { 1: 0, 2: 0, 3: 0, 4: 0, 5: 0 };
    const pazienti = [];                       // [codice, permanenza, attesa, boarding, abbandono]
    const censimento = [];                     // [ora, inAttesa, inTratt, presenti per codice[5], attesa per codice[5]]
    const traiettoria = opz.traiettoria ? [] : null;
    const margineLettiOra = margineLetti(sc) / 24;
    const prio = c => sc.priorita[c];

    function registra(c, t0, att, board, abb) {
      if (t0 >= tInizio && t0 <= tFine) pazienti.push([c, sim.t - t0, att, board, abb ? 1 : 0]);
    }
    function richiestaMedico(c, rival, tBase, poi) {
      let p = (tBase == null ? sim.t : tBase) + prio(c);
      if (rival && sc.rival_precedenza) p = -1e6 + sim.t;
      const req = { prio: p, seq: seq++, fatto: false, concesso: pool => poi(pool) };
      medici.richiedi(req);
      if (ft && ftCodici.has(c) && !req.fatto) ft.richiedi(req);
      return req;
    }
    function durataProcesso(c) {
      if (sc.lungo_quota && sc.lungo_quota[c] != null) {
        if (R.u() < sc.lungo_quota[c]) return R.lognormMu(Math.log(sc.lungo_mediana[c]), sc.lungo_sigma[c]);
        return R.lognormMu(Math.log(sc.breve_mediana[c]), 0.7);
      }
      return R.lognormMu(sc.processo_mu[c], sc.processo_sigma[c]);
    }

    function paziente(c, tArrivo) {
      const t0 = tArrivo == null ? sim.t : tArrivo;
      attesa[c]++;
      let abbandonato = false;
      const req = richiestaMedico(c, false, t0, pool => {
        attesa[c]--;
        const attesaVisita = sim.t - t0;
        tratt[c]++;
        const fast = ft && pool === ft;
        at(sim.t + R.lognormMedia(sc.t_visita[c] * sc.fattore_medico, 0.6), () => {
          pool.rilascia();
          const scala = sc.processo_scala[c] * (1 - (fast ? (sc.ft_riduzione_processo || 0) : 0));
          at(sim.t + scala * durataProcesso(c), () => {
            richiestaMedico(c, true, null, pool2 => {
              at(sim.t + R.lognormMedia(sc.t_rival[c] * sc.fattore_medico, 0.6), () => {
                pool2.rilascia();
                let board = 0;
                const fine = () => { tratt[c]--; registra(c, t0, attesaVisita, board, false); };
                if (R.u() < (sc.p_ricovero[c] || 0)) {
                  board = margineLettiOra > 0 ? R.expo(margineLettiOra) : 720;
                  board = Math.min(board, 720);
                  at(sim.t + board, fine);
                } else fine();
              });
            });
          });
        });
      });
      if (sc.pazienza[c] != null && !req.fatto) {
        at(sim.t + R.expo(1 / sc.pazienza[c]), () => {
          if (!req.fatto) { req.fatto = true; abbandonato = true; attesa[c]--; registra(c, t0, sim.t - t0, 0, true); }
        });
      }
      return abbandonato;
    }

    // arrivi: Poisson non omogeneo (thinning)
    const codici = CODICI.filter(c => sc.arrivi_anno[c] > 0);
    const pesi = codici.map(c => sc.arrivi_anno[c]);
    const tot = pesi.reduce((a, b) => a + b, 0);
    const prof = sc.profilo_arrivi, pmax = Math.max(...prof);
    const lmax = tot / 8760 * pmax;
    function prossimoArrivo() {
      at(sim.t + R.expo(lmax), () => {
        if (sim.t > tFine) return;
        const h = Math.floor(sim.t) % 24;
        if (R.u() < prof[h] / pmax) paziente(R.scegli(codici, pesi));
        prossimoArrivo();
      });
    }
    // cambio d'ora: i pool ricontrollano la capacità
    function tick() {
      medici.distribuisci(); if (ft) ft.distribuisci();
      at(Math.floor(sim.t) + 1, tick);
    }
    function osserva() {
      if (traiettoria) traiettoria.push([sim.t, CODICI.map(c => attesa[c]), CODICI.map(c => tratt[c])]);
      at(sim.t + 0.25, () => {
        if (sim.t >= tInizio && sim.t <= tFine) {
          let a = 0, r = 0;
          CODICI.forEach(c => { a += attesa[c]; r += tratt[c]; });
          censimento.push([Math.floor(sim.t) % 24, a, r, CODICI.map(c => attesa[c] + tratt[c]), CODICI.map(c => attesa[c])]);
        }
        osserva();
      });
    }

    // stato iniziale (gemello): pazienti già presenti
    if (opz.stato) iniettaStato(opz.stato);
    function iniettaStato(st) {
      CODICI.forEach(c => {
        for (let k = 0; k < (st.attesa[c] || 0); k++) paziente(c, sim.t - R.u() * 2 * (opz.attese_medie ? opz.attese_medie[c] : 1));
        for (let k = 0; k < (st.tratt[c] || 0); k++) {
          tratt[c]++;
          const r = opz.residuo ? opz.residuo(c, R) : durataProcesso(c);
          at(sim.t + r, () => { tratt[c]--; });
        }
      });
    }

    prossimoArrivo(); tick(); osserva();
    const fineRun = opz.t0 != null ? tFine + 1e-6 : tFine + 5 * 24;
    while (ev.size && ev.peek().t <= fineRun) {
      const e = ev.pop(); sim.t = e.t; e.fn();
    }
    if (opz.traiettoria) return { traiettoria: traiettoria.filter(x => x[0] >= tInizio && x[0] <= tFine), t0: tInizio };
    return riassumi(sc, pazienti, censimento);
  }

  function ricoveriPsGiorno(sc) {
    return CODICI.reduce((s, c) => s + sc.arrivi_anno[c] * (sc.p_ricovero[c] || 0), 0) / 365;
  }
  function margineLetti(sc) {
    return sc.letti_capacita_giorno - ricoveriPsGiorno(sc) - sc.ricoveri_altri_giorno;
  }

  function media(a) { return a.length ? a.reduce((x, y) => x + y, 0) / a.length : NaN; }

  function riassumi(sc, P, C) {
    const anni = sc.giorni / 365;
    const per = (c, f) => { const v = P.filter(p => p[0] === c).map(f); return media(v); };
    const visti = P.filter(p => !p[4]);
    const pres = C.map(x => x[1] + x[2]), ia = C.map(x => x[1]);
    const q = Math.floor(pres.length / 4);
    const board = P.filter(p => p[3] > 0);
    const r = {
      permanenza: media(P.map(p => p[1])),
      permanenza_codice: {}, p8_codice: {}, p24_codice: {}, attesa_visita_codice: {},
      presenti_codice: {}, in_attesa_codice: {}, accessi_codice: {}, boarding_n_codice: {},
      boarding_ore_codice: {}, abbandoni_codice: {},
      p8: media(P.map(p => p[1] > 8 ? 1 : 0)), p24: media(P.map(p => p[1] > 24 ? 1 : 0)),
      attesa_visita: media(visti.map(p => p[2])),
      in_attesa: media(ia), presenti: media(pres),
      presenti_ora: [], in_attesa_ora: [],
      boarding_n: board.length / anni, boarding_ore: board.length ? media(board.map(p => p[3])) : 0,
      abbandoni: media(P.map(p => p[4])),
      oltre_83: media(pres.map(x => x > 83 ? 1 : 0)),
      accessi: P.length / anni,
      deriva: media(pres.slice(-q)) / media(pres.slice(0, q)),
    };
    r.stabile = r.deriva < 1.15 && margineLetti(sc) > 0;
    for (let h = 0; h < 24; h++) {
      const idx = C.map((x, i) => x[0] === h ? i : -1).filter(i => i >= 0);
      r.presenti_ora.push(media(idx.map(i => pres[i]))); r.in_attesa_ora.push(media(idx.map(i => ia[i])));
    }
    CODICI.forEach((c, i) => {
      r.permanenza_codice[c] = per(c, p => p[1]);
      r.p8_codice[c] = per(c, p => p[1] > 8 ? 1 : 0);
      r.p24_codice[c] = per(c, p => p[1] > 24 ? 1 : 0);
      r.attesa_visita_codice[c] = media(visti.filter(p => p[0] === c).map(p => p[2]));
      r.presenti_codice[c] = media(C.map(x => x[3][i]));
      r.in_attesa_codice[c] = media(C.map(x => x[4][i]));
      r.accessi_codice[c] = P.filter(p => p[0] === c).length / anni;
      const bc = board.filter(p => p[0] === c);
      r.boarding_n_codice[c] = bc.length / anni;
      r.boarding_ore_codice[c] = bc.length ? media(bc.map(p => p[3])) : 0;
      r.abbandoni_codice[c] = per(c, p => p[4]);
    });
    return r;
  }

  /* media di più repliche (semi diversi) */
  function simulaRepliche(sc, repliche) {
    const rr = [];
    for (let k = 0; k < repliche; k++) rr.push(simula(Object.assign({}, sc, { seed: (sc.seed || 42) + 1000 * k })));
    const out = JSON.parse(JSON.stringify(rr[0]));
    const scal = ["permanenza", "p8", "p24", "attesa_visita", "in_attesa", "presenti", "boarding_n", "boarding_ore", "abbandoni", "oltre_83", "accessi", "deriva"];
    scal.forEach(k => out[k] = media(rr.map(r => r[k])));
    out.stabile = rr.every(r => r.stabile);
    ["presenti_ora", "in_attesa_ora"].forEach(k => out[k] = out[k].map((_, i) => media(rr.map(r => r[k][i]))));
    Object.keys(out).filter(k => k.endsWith("_codice")).forEach(k =>
      CODICI.forEach(c => { const v = rr.map(r => r[k][c]).filter(x => !Number.isNaN(x)); out[k][c] = v.length ? media(v) : null; }));
    return out;
  }

  /* ---------------- dai parametri dell'interfaccia allo scenario (porta di app.costruisci) ---------------- */
  function fasceInOrario(fasce) {
    const out = new Array(24).fill(0);
    for (const k in fasce) {
      const [a, b] = k.split("-").map(Number);
      let h = a;
      do { out[h % 24] += Number(fasce[k]); h = (h + 1) % 24; } while (h !== b % 24);
    }
    return out;
  }
  function applicaLeva(sc, l) {
    sc = JSON.parse(JSON.stringify(sc));
    if (l.tipo === "medici") { const add = fasceInOrario(l.fasce); sc.medici_ora = sc.medici_ora.map((v, i) => v + add[i]); }
    else if (l.tipo === "fast_track") {
      const add = fasceInOrario(l.fasce);
      sc.ft_ora = (sc.ft_ora || new Array(24).fill(0)).map((v, i) => v + add[i]);
      sc.ft_codici = l.codici; sc.ft_riduzione_processo = l.riduzione_processo || 0;
    } else if (l.tipo === "letti") sc.letti_capacita_giorno += l.letti / l.degenza_media_giorni;
    else if (l.tipo === "dimissioni") sc.letti_capacita_giorno /= 1 - l.riduzione_degenza;
    else if (l.tipo === "processo") l.codici.forEach(c => sc.processo_scala[c] *= 1 - l.riduzione);
    else if (l.tipo === "deflessione") for (const c in l.quota) sc.arrivi_anno[c] *= 1 - l.quota[c];
    return sc;
  }
  function costruisci(base, p, cfg) {
    let sc = JSON.parse(JSON.stringify(base));
    if (p.medici) sc.medici_ora = fasceInOrario(p.medici);
    sc.fattore_medico *= Number(p.tempo_medico ?? 1);
    const car = Number(p.carico ?? 1), anni = Number(p.anni_avanti ?? 0);
    CODICI.forEach(c => { sc.arrivi_anno[c] *= car * Math.pow(1 + cfg.crescita[c], anni); });
    CODICI.forEach(c => {
      const q = (p.per_codice || {})[c] || {};
      sc.arrivi_anno[c] *= Number(q.accessi ?? 1) * (1 - Number(q.fuori ?? 0));
      sc.processo_scala[c] *= 1 - Number(q.processo ?? 0);
      if (q.ricovero != null) sc.p_ricovero[c] = Math.min(1, sc.p_ricovero[c] * Number(q.ricovero));
    });
    sc.letti_capacita_giorno += Number(p.letti_extra ?? 0) / Number(p.degenza_giorni ?? 8);
    sc.letti_capacita_giorno /= 1 - Number(p.riduzione_degenza ?? 0);
    if (p.letti_seguono_ricoveri && anni) sc.letti_capacita_giorno += ricoveriPsGiorno(sc) - ricoveriPsGiorno(base);
    for (const c in sc.pazienza) sc.pazienza[c] *= Number(p.pazienza ?? 1);
    (p.leve || []).forEach(id => { const l = cfg.leve.find(x => x.id === id); if (l) sc = applicaLeva(sc, l); });
    return sc;
  }
  function costoAnnuo(p, cfg) {
    const leve = cfg.leve, base = cfg.config.turni_medici[p.turni || cfg.config.turni_medici.scenario];
    const cm = leve.find(l => l.id === "medico_20_02").costo_annuo, voci = [];
    Object.keys(base).forEach(f => {
      const d = Number((p.medici || {})[f] ?? base[f]) - Number(base[f]);
      if (d) voci.push([`${d > 0 ? "+" : ""}${d} medici ${f}`, d * cm]);
    });
    const le = Number(p.letti_extra || 0);
    if (le) voci.push([`${le > 0 ? "+" : ""}${le} letti`, le * 365 * 600]);
    (p.leve || []).forEach(id => { const l = leve.find(x => x.id === id); if (l) voci.push([l.nome, l.costo_annuo]); });
    return { voci, totale: voci.reduce((s, v) => s + v[1], 0) };
  }

  /* ---------------- previsione con il metodo degli analoghi (porta di gemello.prevedi_analoghi) ---------------- */
  function percentile(arr, p) {
    const a = arr.slice().sort((x, y) => x - y); if (!a.length) return NaN;
    const i = (a.length - 1) * p / 100, lo = Math.floor(i), hi = Math.ceil(i);
    return a[lo] + (a[hi] - a[lo]) * (i - lo);
  }
  function prevediAnaloghi(lib, stato, ora, orizzonte, o) {
    const k = o.k || 60, tau = o.tau || 24, fin = o.finestra_ore || 1, allarga = o.allarga || 1;
    const oA = CODICI.map(c => stato.attesa[c] || 0), oR = CODICI.map(c => stato.tratt[c] || 0);
    const passi = Math.round(orizzonte * 4);
    const cand = [];
    lib.forEach((tr, ir) => {
      for (let i = 0; i + passi < tr.length; i++) {
        const h = tr[i][0] % 24, d = Math.abs(((h - ora + 12) % 24 + 24) % 24 - 12);
        if (d > fin) continue;
        let s = 0;
        for (let j = 0; j < 5; j++) {
          const da = (tr[i][1][j] - oA[j]) / 3, dr = (tr[i][2][j] - oR[j]) / Math.sqrt(Math.max(oR[j], 4));
          s += da * da + dr * dr;
        }
        cand.push([Math.sqrt(s), ir, i]);
      }
    });
    cand.sort((a, b) => a[0] - b[0]);
    const scelti = cand.slice(0, k);
    const ore = Array.from({ length: passi + 1 }, (_, i) => i / 4);
    const pres = [], att = [], perCod = CODICI.map(() => []), attCod = CODICI.map(() => []);
    scelti.forEach(([, ir, i]) => {
      const tr = lib[ir], pr = [], at = [], pc = CODICI.map(() => []), ac = CODICI.map(() => []);
      for (let s = 0; s <= passi; s++) {
        const dec = Math.exp(-ore[s] / tau);
        let tp = 0, ta = 0;
        for (let j = 0; j < 5; j++) {
          const a = Math.max(0, tr[i + s][1][j] + (oA[j] - tr[i][1][j]) * dec);
          const r = Math.max(0, tr[i + s][2][j] + (oR[j] - tr[i][2][j]) * dec);
          tp += a + r; ta += a; pc[j].push(a + r); ac[j].push(a);
        }
        pr.push(tp); at.push(ta);
      }
      pres.push(pr); att.push(at); pc.forEach((v, j) => perCod[j].push(v)); ac.forEach((v, j) => attCod[j].push(v));
    });
    if (o.correzione) {                         // differenza di forma oraria reale - modello
      const [real, mod] = o.correzione;
      const h0 = Math.floor(ora) % 24;
      const corr = (R, M, s) => { const hh = Math.floor(ora + ore[s]) % 24; return (R[hh] - M[hh]) - (R[h0] - M[h0]); };
      pres.forEach(pr => pr.forEach((v, s) => pr[s] = Math.max(0, v + corr(real.presenti, mod.presenti, s))));
      att.forEach(a => a.forEach((v, s) => a[s] = Math.max(0, v + corr(real.in_attesa, mod.in_attesa, s))));
    }
    const pct = M => {
      const out = { "10": [], "50": [], "90": [] };
      for (let s = 0; s <= passi; s++) {
        const col = M.map(r => r[s]), m = percentile(col, 50);
        out["50"].push(m);
        out["10"].push(Math.max(0, m + allarga * (percentile(col, 10) - m)));
        out["90"].push(Math.max(0, m + allarga * (percentile(col, 90) - m)));
      }
      return out;
    };
    const pc = {}, ac = {};
    CODICI.forEach((c, j) => { pc[c] = pct(perCod[j]); ac[c] = pct(attCod[j]); });
    const prob = {};
    [83, 120, 150].forEach(s => { prob[s] = ore.map((_, i) => media(pres.map(r => r[i] > s ? 1 : 0))); });
    return { ore, presenti: pct(pres), in_attesa: pct(att), per_codice: pc, attesa_codice: ac, prob_oltre: prob };
  }
  function libreria(sc, giorni, repliche) {
    const out = [];
    for (let k = 0; k < repliche; k++) {
      const s2 = Object.assign({}, sc, { giorni, seed: (sc.seed || 42) + 7919 * (k + 1) });
      out.push(simula(s2, { traiettoria: true }).traiettoria);
    }
    return out;
  }
  function profiloModello(lib) {
    const P = Array.from({ length: 24 }, () => []), A = Array.from({ length: 24 }, () => []);
    lib.forEach(tr => tr.forEach(x => {
      const h = Math.floor(x[0]) % 24; const a = x[1].reduce((s, v) => s + v, 0);
      P[h].push(a + x[2].reduce((s, v) => s + v, 0)); A[h].push(a);
    }));
    return { presenti: P.map(media), in_attesa: A.map(media) };
  }

  const Motore = { simula, simulaRepliche, costruisci, costoAnnuo, fasceInOrario, applicaLeva, margineLetti,
    ricoveriPsGiorno, prevediAnaloghi, libreria, profiloModello, CODICI };
  if (typeof module !== "undefined" && module.exports) module.exports = Motore;
  else root.Motore = Motore;
})(typeof self !== "undefined" ? self : this);
