/* Web Worker: esegue le simulazioni nel browser senza bloccare la pagina (versione online). */
importScripts("motore.js");
const M = self.Motore;
let CFG = null;
const SCENARI = {}, CACHE_REGIME = {}, CACHE_LIB = {};

async function json(url) { const r = await fetch(url); if (!r.ok) throw new Error("manca " + url); return r.json(); }
const intKeys = o => { const out = {}; for (const k in o) out[k] = o[k]; return out; };

async function base(p) {
  const prec = p.rivalutazione_precedenza ?? CFG.config.rivalutazione_precedenza;
  const v = (p.turni || CFG.config.turni_medici.scenario) + (prec ? "_rivprec" : "");
  if (!SCENARI[v]) {
    if (!CFG.scenari_calibrati.includes(v)) throw new Error(`Scenario ${v} non calibrato`);
    SCENARI[v] = await json(`dati/scenario_${v}.json`);
  }
  return { v, sc: SCENARI[v] };
}
const chiave = sc => JSON.stringify(sc, (k, x) => k === "nome" ? undefined : (typeof x === "number" ? Math.round(x * 1e9) / 1e9 : x));
const web = () => CFG.config.gemello.web || { giorni: 120, repliche: 4, ottimizza_giorni: 120, ottimizza_repliche: 3, lib_giorni: 120, lib_repliche: 6 };

function regimeDi(sc, giorni, rep) {
  const k = chiave(sc) + giorni + "/" + rep;
  if (!CACHE_REGIME[k]) CACHE_REGIME[k] = M.simulaRepliche(Object.assign({}, sc, { giorni }), rep);
  return CACHE_REGIME[k];
}

function metrica(r, nome) {
  if (nome === "permanenza") return r.permanenza;
  if (nome === "attesa") return r.attesa_visita;
  if (nome === "presenti") return r.presenti;
  const [tipo, c] = nome.split("_c");
  return (tipo === "permanenza" ? r.permanenza_codice : r.attesa_visita_codice)[c];
}

const lavori = {
  async init(m) { CFG = m.cfg; return true; },

  async regime(m) {
    const { sc: b } = await base(m.p);
    const s = M.costruisci(b, m.p, CFG);
    const w = web();
    return { modificato: chiave(s) !== chiave(b), base: regimeDi(b, w.giorni, w.repliche), scenario: regimeDi(s, w.giorni, w.repliche),
      reale: CFG.reale, costo: M.costoAnnuo(m.p, CFG), margine_letti_giorno: M.margineLetti(s) };
  },

  // differenza scenario - base nella previsione delle prossime ore (si somma alla previsione pubblicata)
  async delta(m) {
    const { sc: b } = await base(m.p);
    const s = M.costruisci(b, m.p, CFG);
    if (chiave(s) === chiave(b)) return { modificato: false };
    const w = web(), a = CFG.config.gemello.analoghi;
    const lib = sc => { const k = chiave(sc); if (!CACHE_LIB[k]) CACHE_LIB[k] = M.libreria(sc, w.lib_giorni, w.lib_repliche); return CACHE_LIB[k]; };
    const o = { k: a.k, tau: a.tau, finestra_ore: a.finestra_ore, allarga: 1 };
    const fb = M.prevediAnaloghi(lib(b), m.stato, m.ora, m.orizzonte, o);
    const fs = M.prevediAnaloghi(lib(s), m.stato, m.ora, m.orizzonte, o);
    return { modificato: true, fb, fs };
  },

  async ottimizza(m, prog) {
    const { sc: b } = await base(m.p);
    const sc0 = M.costruisci(b, m.p, CFG);
    const w = web();
    const val = sc => regimeDi(sc, w.ottimizza_giorni, w.ottimizza_repliche);
    prog(0.03, "simulazione di partenza");
    const r0 = val(sc0), m0 = metrica(r0, m.metrica);
    const singole = CFG.leve.map((l, i) => {
      prog(0.05 + 0.25 * i / CFG.leve.length, "leva: " + l.nome);
      const r = val(M.applicaLeva(sc0, l));
      return { nome: l.nome, id: l.id, effetto: 1 - metrica(r, m.metrica) / m0, costo: l.costo_annuo, attesa: r.attesa_visita, oltre_83: r.oltre_83 };
    }).sort((x, y) => y.effetto / y.costo - x.effetto / x.costo);
    // unità (leve ripetibili)
    let disp = [];
    CFG.leve.forEach(l => { const n = l.max_unita || 1; for (let k = 1; k <= n; k++) disp.push(Object.assign({}, l, { unita: k, etichetta: l.nome + (n > 1 ? ` (unità ${k})` : "") })); });
    let cur = sc0, mcur = m0, rcur = r0;
    const passi = [], scelte = [];
    while (disp.length && 1 - mcur / m0 < m.target) {
      const cand = disp.filter(u => u.unita === 1 || scelte.some(s => s.id === u.id && s.unita === u.unita - 1));
      let best = null;
      cand.forEach(u => {
        const r = val(M.applicaLeva(cur, u)), g = (mcur - metrica(r, m.metrica)) / m0;
        const score = g / u.costo_annuo;
        if (!best || score > best.score) best = { u, r, g, score };
      });
      if (!best || best.g <= 0.002) break;
      scelte.push(best.u); disp = disp.filter(x => x !== best.u);
      cur = M.applicaLeva(cur, best.u); mcur = metrica(best.r, m.metrica); rcur = best.r;
      passi.push({ leva: best.u.etichetta, guadagno: best.g, cumulato: 1 - mcur / m0, costo: best.u.costo_annuo });
      prog(Math.min(0.97, 0.3 + 0.06 * passi.length), "+ " + best.u.etichetta);
    }
    return { target: m.target, metrica: m.metrica, metrica_nome: CFG.metriche[m.metrica], valore_partenza: m0, valore_finale: mcur,
      partenza: r0, finale: rcur, singole, passi, raggiunto: 1 - mcur / m0 };
  },

  async validazione_storica(m, prog) {
    const { sc: b } = await base(m.p);
    const st = await json("dati/storico.json");
    const w = web(), righe = [];
    const anni = Object.keys(st.serie).filter(a => !st.serie[a].anomalo);
    anni.forEach((a, i) => {
      prog(i / anni.length, "anno " + a);
      const s = st.serie[a], sc = JSON.parse(JSON.stringify(b));
      M.CODICI.forEach(c => sc.arrivi_anno[c] = s.accessi[c]);
      const r = regimeDi(sc, w.giorni, w.repliche);
      const codici = {}; M.CODICI.forEach(c => codici[c] = { reale: s.permanenza[c], sim: r.permanenza_codice[c] });
      righe.push({ anno: +a, accessi: s.totale, permanenza_reale: s.permanenza_media, permanenza_sim: r.permanenza, codici,
        boarding_reale: s.boarding_ore, boarding_sim: r.boarding_ore });
    });
    return { righe };
  },
};

self.onmessage = async e => {
  const m = e.data;
  const prog = (x, msg) => self.postMessage({ id: m.id, progresso: x, messaggio: msg });
  try { self.postMessage({ id: m.id, risultato: await lavori[m.tipo](m, prog) }); }
  catch (err) { self.postMessage({ id: m.id, errore: String(err.message || err) }); }
};
