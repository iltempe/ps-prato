/* Versione online (pspratolive.it): stessa interfaccia, ma al posto del server Python
   - dati pubblicati in dati/*.json (previsione aggiornata ogni 15 minuti dalla GitHub Action)
   - simulazioni nel browser con il motore JavaScript (worker.js + motore.js). */
const Statico = (() => {
  let cfg = null, worker = null, id = 1;
  const attese = new Map();
  const json = async url => { const r = await fetch(url, { cache: "no-store" }); if (!r.ok) throw new Error("dato non disponibile: " + url); return r.json(); };

  function chiama(tipo, dati, onProg) {
    return new Promise((res, rej) => {
      const k = id++;
      attese.set(k, { res, rej, onProg });
      worker.postMessage(Object.assign({ id: k, tipo }, dati));
    });
  }

  async function init() {
    cfg = await json("dati/config.json");
    worker = new Worker("worker.js");
    worker.onmessage = e => {
      const m = e.data, a = attese.get(m.id);
      if (!a) return;
      if (m.progresso != null) { a.onProg && a.onProg(m.progresso, m.messaggio); return; }
      attese.delete(m.id);
      m.errore ? a.rej(new Error(m.errore)) : a.res(m.risultato);
    };
    await chiama("init", { cfg });
    return cfg;
  }

  async function stato() {
    const p = await json("dati/previsione.json");
    return { ultimo: p.ultimo, live_errore: null, live_letto: p.generato, storia: p.storia, _prev: p };
  }

  async function prevedi(body) {
    const pub = (await json("dati/previsione.json")).previsione;
    const oriz = Math.min(Number(body.orizzonte || 12), pub.ore[pub.ore.length - 1]);
    const n = pub.ore.filter(h => h <= oriz + 1e-9).length;
    const taglia = o => Array.isArray(o) ? o.slice(0, n) : Object.fromEntries(Object.entries(o).map(([k, v]) => [k, taglia(v)]));
    const base = taglia({ ore: pub.ore, presenti: pub.presenti, in_attesa: pub.in_attesa, per_codice: pub.per_codice,
      attesa_codice: pub.attesa_codice, prob_oltre: pub.prob_oltre });
    const reg = await chiama("regime", { p: body });
    if (!reg.modificato) return { base, scenario: base, inizio: pub.inizio, modificato: false };
    // Scenario = previsione pubblicata + differenza di regime (scenario - base) ora per ora,
    // che entra gradualmente: il PS parte dallo stato reale di adesso e converge verso il nuovo
    // regime con i suoi tempi (attesa della visita: ~1 h; presenti: ~ la permanenza media).
    const t0 = new Date(pub.inizio), h0 = t0.getHours() + t0.getMinutes() / 60;
    const b = reg.base, s = reg.scenario;
    const tauA = Math.max(0.5, b.attesa_visita), tauP = Math.max(2, b.permanenza);
    const ora = x => Math.floor(h0 + x) % 24;
    // se cambiano solo i medici, l'effetto parte dalla prima ora in cui il turno è diverso
    const tOn = inizioEffetto(body, h0);
    const f = (x, tau) => x < tOn ? 0 : 1 - Math.exp(-(x - tOn) / tau);
    const dPres = base.ore.map(x => f(x, tauP) * (s.presenti_ora[ora(x)] - b.presenti_ora[ora(x)]));
    const dAtt = base.ore.map(x => f(x, tauA) * (s.in_attesa_ora[ora(x)] - b.in_attesa_ora[ora(x)]));
    const sposta = (P, d) => Object.fromEntries(Object.keys(P).map(q => [q, P[q].map((v, i) => Math.max(0, v + d[i]))]));
    const scen = { ore: base.ore, presenti: sposta(base.presenti, dPres), in_attesa: sposta(base.in_attesa, dAtt),
      per_codice: {}, attesa_codice: {}, prob_oltre: {} };
    [1, 2, 3, 4, 5].forEach(c => {
      const dp = base.ore.map(x => f(x, tauP) * ((s.presenti_codice[c] || 0) - (b.presenti_codice[c] || 0)));
      const da = base.ore.map(x => f(x, tauA) * ((s.in_attesa_codice[c] || 0) - (b.in_attesa_codice[c] || 0)));
      scen.per_codice[c] = sposta(base.per_codice[c], dp);
      scen.attesa_codice[c] = sposta(base.attesa_codice[c], da);
    });
    // probabilità oltre soglia: distribuzione pubblicata spostata (approssimazione normale)
    const Phi = z => 0.5 * (1 + Math.tanh(0.7978845608 * (z + 0.044715 * z * z * z)));
    Object.keys(base.prob_oltre).forEach(soglia => {
      scen.prob_oltre[soglia] = base.ore.map((x, i) => {
        const m = base.presenti["50"][i], sd = Math.max(1, (base.presenti["90"][i] - base.presenti["10"][i]) / 2.563);
        const pb = base.prob_oltre[soglia][i], zb = (m - +soglia) / sd, zs = (m + dPres[i] - +soglia) / sd;
        return Math.min(1, Math.max(0, pb + Phi(zs) - Phi(zb)));
      });
    });
    return { base, scenario: scen, inizio: pub.inizio, modificato: true };
  }

  function inizioEffetto(p, h0) {
    const d = { medici: true };
    const soloMedici = !(p.leve && p.leve.length) && !p.letti_seguono_ricoveri &&
      ["tempo_medico", "carico", "pazienza"].every(k => (p[k] ?? 1) === 1) &&
      ["anni_avanti", "letti_extra", "riduzione_degenza"].every(k => !(p[k] || 0)) &&
      Object.values(p.per_codice || {}).every(q => (q.accessi ?? 1) === 1 && !(q.processo || 0) && !(q.fuori || 0) && (q.ricovero ?? 1) === 1) &&
      (p.turni || cfg.config.turni_medici.scenario) === cfg.config.turni_medici.scenario;
    if (!soloMedici || !p.medici) return 0;
    const orario = m => { const o = new Array(24).fill(0); for (const k in m) { const [a, z] = k.split("-").map(Number); let h = a; do { o[h % 24] += +m[k]; h = (h + 1) % 24; } while (h !== z % 24); } return o; };
    const ob = orario(cfg.config.turni_medici[p.turni || cfg.config.turni_medici.scenario]), os = orario(p.medici);
    for (let x = 0; x < 48; x++) { const h = Math.floor(h0 + x) % 24; if (ob[h] !== os[h]) return x === 0 ? 0 : Math.ceil(h0 + x) - h0 - (Math.ceil(h0) === h0 ? 0 : 1) ; }
    return 0;
  }

  async function api(path, body) {
    if (path === "/api/config") return Object.assign({ statico: true }, cfg);
    if (path === "/api/stato") return stato();
    if (path === "/api/prevedi") return prevedi(body || {});
    if (path === "/api/regime") return chiama("regime", { p: body || {} });
    if (path === "/api/storico") return json("dati/storico.json");
    throw new Error("Funzione disponibile solo nella versione locale");
  }

  async function lavoro(tipo, body, onProg) {
    if (tipo === "backtest") return (await json("dati/affidabilita.json")).backtest;
    if (tipo === "ottimizza") return chiama("ottimizza", { p: body, target: body.target, metrica: body.metrica }, onProg);
    if (tipo === "validazione_storica") return chiama("validazione_storica", { p: body }, onProg);
    throw new Error("La calibrazione è disponibile solo nella versione locale");
  }

  return { init, api, lavoro, json };
})();
