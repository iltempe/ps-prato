/* Interfaccia del gemello digitale. Tutto passa dalle API di app.py. */
const $ = s => document.querySelector(s);
let STATICO = false;   // true su pspratolive.it: niente server, simulazioni nel browser
const API = (path, body) => STATICO ? Statico.api(path, body) : APIremota(path, body);
const APIremota = (path, body) => fetch(path, body === undefined ? {} : {
  method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body)
}).then(async r => { const j = await r.json(); if (!r.ok) throw new Error(j.errore || r.statusText); return j; });

const css = v => getComputedStyle(document.body).getPropertyValue(v).trim();
const COL = () => ({ obs: css("--observed"), base: css("--base"), baseBand: css("--base-band"),
  sc: css("--series-1"), scBand: css("--series-1-band"),
  cat: [1, 2, 3, 4, 5].map(i => css("--cat-" + i)) });
const NOMI_COD = { 1: "1 Emergenza", 2: "2 Urg. indifferibile", 3: "3 Urg. differibile", 4: "4 Urg. minore", 5: "5 Non urgenza" };
const COLORE_COD = { 1: "rosso", 2: "giallo", 3: "verde", 4: "azzurro", 5: "bianco" };
const f0 = v => v == null ? "—" : Math.round(v).toLocaleString("it-IT");
const f1 = v => v == null ? "—" : v.toLocaleString("it-IT", { maximumFractionDigits: 1, minimumFractionDigits: 1 });
const pct = (v, d = 0) => v == null ? "—" : (v * 100).toLocaleString("it-IT", { maximumFractionDigits: d, minimumFractionDigits: d }) + "%";
const ore = v => v == null ? "—" : (v < 1 ? Math.round(v * 60) + "′" : Math.floor(v) + "h " + String(Math.round((v % 1) * 60)).padStart(2, "0") + "′");
const euro = v => (v / 1e3).toLocaleString("it-IT", { maximumFractionDigits: 0 }) + " k€";
const hhmm = ms => new Date(ms).toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" });
const giornoOra = ms => new Date(ms).toLocaleString("it-IT", { weekday: "short", hour: "2-digit", minute: "2-digit" });

let CFG = null, P = null, ULTIMO_TS = null, STATO = null;

/* ------------------------------------------------------------------ parametri */
const SLIDERS = [
  { id: "tempo_medico", lbl: "Tempo medico per paziente", min: 0.7, max: 1.3, step: 0.05, def: 1, fmt: v => "×" + v.toFixed(2), aiuto: "1 = valore calibrato sui dati" },
  { id: "carico", lbl: "Accessi", min: 0.7, max: 1.5, step: 0.05, def: 1, fmt: v => "×" + v.toFixed(2), aiuto: "moltiplicatore sugli accessi 2025" },
  { id: "anni_avanti", lbl: "Anni nel futuro", min: 0, max: 10, step: 1, def: 0, fmt: v => v ? "+" + v + " (" + (2025 + v) + ")" : "0 (2025)", aiuto: "crescita per codice dai dati ASL 2022-2025" },
  { id: "pazienza", lbl: "Pazienza prima di abbandonare", min: 0.5, max: 2, step: 0.1, def: 1, fmt: v => "×" + v.toFixed(1), aiuto: "più pazienza = meno abbandoni, più persone in attesa" },
  { id: "letti_extra", lbl: "Letti in più nei reparti", min: -20, max: 80, step: 5, def: 0, fmt: v => (v > 0 ? "+" : "") + v, aiuto: "degenza media 8 giorni" },
  { id: "riduzione_degenza", lbl: "Degenza media in reparto", min: 0, max: 0.15, step: 0.01, def: 0, fmt: v => v ? "−" + pct(v) : "invariata", aiuto: "bed management, dimissioni al mattino e nel weekend" },
];

function slider(host, s, value, onInput) {
  const div = document.createElement("div");
  div.className = "slider";
  div.innerHTML = `<div class="lbl"><span>${s.lbl}</span><span class="val"></span></div>
    <input type="range" min="${s.min}" max="${s.max}" step="${s.step}" value="${value}" aria-label="${s.lbl}">
    ${s.aiuto ? `<div class="aiuto">${s.aiuto}</div>` : ""}`;
  const inp = div.querySelector("input"), val = div.querySelector(".val");
  const upd = () => { const v = +inp.value; val.textContent = s.fmt(v); val.classList.toggle("mod", v !== s.def); };
  inp.addEventListener("input", () => { upd(); onInput(+inp.value); });
  upd();
  host.innerHTML = ""; host.appendChild(div);
}

function parametriDefault() {
  const t = CFG.config.turni_medici.scenario;
  const p = { turni: t, rivalutazione_precedenza: !!CFG.config.rivalutazione_precedenza, medici: { ...CFG.config.turni_medici[t] }, leve: [],
    letti_seguono_ricoveri: false, orizzonte: 12, per_codice: {} };
  [1, 2, 3, 4, 5].forEach(c => p.per_codice[c] = { accessi: 1, processo: 0, fuori: 0, ricovero: 1 });
  SLIDERS.forEach(s => p[s.id] = s.def);
  return p;
}

function disegnaParametri() {
  $("#p-turni").value = P.turni;
  $("#p-rivprec").checked = P.rivalutazione_precedenza;
  $("#p-letti_seguono").checked = P.letti_seguono_ricoveri;
  const base = CFG.config.turni_medici[P.turni];
  const host = $("#p-medici"); host.innerHTML = "";
  CFG.fasce.forEach(f => {
    const d = document.createElement("div"); host.appendChild(d);
    slider(d, { id: "m" + f, lbl: "Fascia " + f, min: 0, max: 14, step: 1, def: base[f],
      fmt: v => v + (v !== base[f] ? ` (${v > base[f] ? "+" : ""}${v - base[f]})` : "") }, P.medici[f],
      v => { P.medici[f] = v; cambiato(); });
  });
  SLIDERS.forEach(s => slider($("#r-" + s.id), s, P[s.id], v => { P[s.id] = v; cambiato(); }));
  disegnaParCodice();
  const lh = $("#p-leve"); lh.innerHTML = "";
  CFG.leve.forEach(l => {
    const lab = document.createElement("label"); lab.className = "check";
    lab.innerHTML = `<input type="checkbox" value="${l.id}" ${P.leve.includes(l.id) ? "checked" : ""}> <span>${l.nome} <span class="badge">${euro(l.costo_annuo)}/anno</span></span>`;
    lab.querySelector("input").addEventListener("change", e => {
      P.leve = e.target.checked ? [...P.leve, l.id] : P.leve.filter(x => x !== l.id); cambiato();
    });
    lh.appendChild(lab);
  });
  const variante = P.turni + (P.rivalutazione_precedenza ? "_rivprec" : "");
  $("#nota-scenari").innerHTML = CFG.scenari_calibrati.includes(variante)
    ? `Scenario calibrato: <code>${variante}</code>`
    : `<span class="errore">Scenario <code>${variante}</code> non ancora calibrato: vai su Affidabilità → Calibrazione.</span>`;
}

/* parametri per codice */
let COD_SEL = 3;
const SLIDERS_COD = [
  { k: "accessi", lbl: "Accessi", min: 0.5, max: 2, step: 0.05, def: 1, fmt: v => "×" + v.toFixed(2), aiuto: "moltiplicatore sugli accessi di questo codice" },
  { k: "processo", lbl: "Tempo tra visita e decisione", min: 0, max: 0.6, step: 0.05, def: 0, fmt: v => v ? "−" + pct(v) : "invariato", aiuto: "esami, consulenze, osservazione (es. diagnostica dedicata)" },
  { k: "fuori", lbl: "Gestiti fuori dal PS", min: 0, max: 0.8, step: 0.05, def: 0, fmt: v => pct(v), aiuto: "CAU, case di comunità, medici di famiglia", codici: [3, 4, 5] },
  { k: "ricovero", lbl: "Probabilità di ricovero", min: 0.5, max: 1.5, step: 0.05, def: 1, fmt: v => "×" + v.toFixed(2), aiuto: "chi viene ricoverato può finire in boarding", codici: [1, 2, 3, 4] },
];
const codModificato = c => SLIDERS_COD.some(s => P.per_codice[c][s.k] !== s.def);
function bottoniCodice(host, sel, onClick, conMod) {
  const C = COL();
  host.innerHTML = [1, 2, 3, 4, 5].map(c => `<button data-c="${c}" class="${c === sel ? "attivo" : ""}" title="${NOMI_COD[c]}">
    <i style="background:${C.cat[c - 1]}"></i>Codice ${c}${conMod && codModificato(c) ? '<span class="mod"></span>' : ""}</button>`).join("");
  host.querySelectorAll("button").forEach(b => b.addEventListener("click", () => onClick(+b.dataset.c)));
}
function disegnaParCodice() {
  bottoniCodice($("#p-sel-codice"), COD_SEL, c => { COD_SEL = c; disegnaParCodice(); }, true);
  const host = $("#p-codice"); host.innerHTML = `<p class="nota"><b>${NOMI_COD[COD_SEL]}</b> (${COLORE_COD[COD_SEL]} nel feed) · ${f0(CFG.asl.accessi[COD_SEL])} accessi nel ${CFG.asl.anno}, permanenza media ${ore(CFG.asl.permanenza[COD_SEL])}</p>`;
  SLIDERS_COD.filter(s => !s.codici || s.codici.includes(COD_SEL)).forEach(s => {
    const d = document.createElement("div"); host.appendChild(d);
    slider(d, s, P.per_codice[COD_SEL][s.k], v => { P.per_codice[COD_SEL][s.k] = v; bottoniCodice($("#p-sel-codice"), COD_SEL, c => { COD_SEL = c; disegnaParCodice(); }, true); cambiato(); });
  });
}

$("#p-turni").addEventListener("change", e => {
  P.turni = e.target.value; P.medici = { ...CFG.config.turni_medici[P.turni] }; disegnaParametri(); cambiato();
});
$("#p-rivprec").addEventListener("change", e => { P.rivalutazione_precedenza = e.target.checked; disegnaParametri(); cambiato(); });
$("#p-letti_seguono").addEventListener("change", e => { P.letti_seguono_ricoveri = e.target.checked; cambiato(); });
$("#p-orizzonte").addEventListener("change", e => { P.orizzonte = +e.target.value; $("#oriz-lbl").textContent = P.orizzonte; aggiornaPrevisione(); });
$("#reset").addEventListener("click", () => { P = parametriDefault(); disegnaParametri(); cambiato(); });

let timer = null;
function cambiato() {
  clearTimeout(timer);
  timer = setTimeout(() => { aggiornaPrevisione(); REGIME_STALE = true; if (tabAttiva() === "regime") aggiornaRegime(); }, 500);
}

/* ------------------------------------------------------------------ schede */
let SCHEDA = "adesso";
const tabAttiva = () => SCHEDA;
function vaiA(tab) {
  SCHEDA = tab;
  const testo = tab === "istruzioni" || tab === "metodo";
  document.body.classList.toggle("lettura", testo);
  document.querySelectorAll(".sotto-nav a").forEach(a => {
    const on = a.dataset.sotto === (testo ? tab : "strumenti");
    on ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current");
  });
  document.querySelectorAll(".schede button").forEach(b => b.classList.toggle("attiva", b.dataset.tab === tab));
  document.querySelectorAll(".scheda").forEach(s => s.classList.toggle("attiva", s.id === "tab-" + tab));
  if (tab === "regime" && REGIME_STALE) aggiornaRegime();
  if (tab === "storico" && !STORICO) caricaStorico();
  if (tab === "adesso" && ULTIMA_PREV) disegnaPrevisione(ULTIMA_PREV);
  if (tab === "istruzioni" || tab === "metodo") caricaTesto(tab);
  history.replaceState(null, "", "#" + tab);
}
const TESTI = {};
async function caricaTesto(tab) {
  if (TESTI[tab]) return;
  const box = $("#doc-" + tab);
  try {
    const r = await fetch(tab + ".frag.html", { cache: "no-store" });
    if (!r.ok) throw new Error(r.statusText);
    box.innerHTML = await r.text();
    TESTI[tab] = true;
  } catch (e) { box.innerHTML = `<p class="errore">Testo non disponibile (${e.message}).</p>`; }
}
// link "data-goto" ovunque nella pagina, anche dentro i testi caricati
document.addEventListener("click", e => {
  const a = e.target.closest("[data-goto]");
  if (!a) return;
  e.preventDefault(); vaiA(a.dataset.goto); window.scrollTo({ top: 0, behavior: "smooth" });
});
document.querySelectorAll(".schede button").forEach(b => b.addEventListener("click", () => vaiA(b.dataset.tab)));

/* ------------------------------------------------------------------ live */
async function aggiornaStato() {
  try {
    STATO = await API("/api/stato");
    const u = STATO.ultimo, ts = new Date(u.ts);
    const eta = Math.round((Date.now() - ts) / 60000);
    const quando = ts.toLocaleString("it-IT", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
    const durata = eta < 120 ? eta + " min" : (eta / 60).toLocaleString("it-IT", { maximumFractionDigits: 1 }) + " ore";
    const fresco = eta < 45 && !STATO.live_errore;
    $("#live-punto").className = "punto " + (fresco ? "ok" : "ko");
    $("#live-testo").textContent = fresco
      ? `Dati in tempo reale · rilevazione ${quando} (${durata} fa)`
      : `Dati fermi: ultima rilevazione ${quando}, nessun dato nuovo da ${durata} (la fonte ASL non risponde). Previsione calcolata da quel momento.`;
    $("#live").title = fresco ? "" : "Il campionamento riprova ogni 15 minuti e riprende da solo quando la fonte torna disponibile.";
    if (u.ts !== ULTIMO_TS) { ULTIMO_TS = u.ts; aggiornaPrevisione(); }
    disegnaStato();
  } catch (e) { $("#live-testo").textContent = "server non raggiungibile: " + e.message; $("#live-punto").className = "punto ko"; }
}

function disegnaStato() {
  const u = STATO.ultimo;
  let righe = "", ta = 0, tt = 0;
  for (let c = 1; c <= 5; c++) {
    const a = u.attesa[c] || 0, t = u.tratt[c] || 0; ta += a; tt += t;
    righe += `<tr><td>${NOMI_COD[c]} <span class="badge">${COLORE_COD[c]}</span></td><td>${a}</td><td>${t}</td><td>${a + t}</td></tr>`;
  }
  $("#tab-stato").innerHTML = `<table><thead><tr><th>Codice (colore nel feed)</th><th>In attesa</th><th>In trattamento</th><th>Totale</th></tr></thead>
    <tbody>${righe}<tr><th>Totale</th><th>${ta}</th><th>${tt}</th><th>${ta + tt}</th></tr></tbody></table>
    <p class="nota">Fonte: ${u.fonte}. Corrispondenza colori→codici ricavata con la Legge di Little sui dati ASL.</p>`;
}

/* ------------------------------------------------------------------ previsione */
let ULTIMA_PREV = null, REQ_PREV = 0;
async function aggiornaPrevisione() {
  if (!P) return;
  const id = ++REQ_PREV;
  document.querySelectorAll("#tab-adesso .chart").forEach(c => c.classList.add("caricamento"));
  try {
    const r = await API("/api/prevedi", P);
    if (id !== REQ_PREV) return;
    ULTIMA_PREV = r; disegnaPrevisione(r);
  } catch (e) {
    $("#ch-presenti").innerHTML = `<p class="errore">${e.message}</p>`;
  } finally {
    if (id === REQ_PREV) document.querySelectorAll("#tab-adesso .chart").forEach(c => c.classList.remove("caricamento"));
  }
}

function disegnaPrevisione(r) {
  if (tabAttiva() !== "adesso") return;
  const C = COL(), t0 = new Date(r.inizio).getTime();
  const xs = r.base.ore.map(h => t0 + h * 3600e3);
  const hs = STATO ? STATO.storia.ts.map(t => new Date(t).getTime()) : [];
  const soglia = CFG.config.gemello.soglia_affollamento;
  const mod = r.modificato;
  const serie = (k) => {
    const s = [{ name: "Osservato", x: hs, y: STATO ? STATO.storia[k] : [], color: C.obs }];
    s.push({ name: mod ? "Base" : "Previsione", x: xs, y: r.base[k]["50"], color: mod ? C.base : C.sc, dash: mod ? "5 4" : "",
      band: { lo: r.base[k]["10"], hi: r.base[k]["90"], color: mod ? C.baseBand : C.scBand } });
    if (mod) s.push({ name: "Con i parametri scelti", x: xs, y: r.scenario[k]["50"], color: C.sc,
      band: { lo: r.scenario[k]["10"], hi: r.scenario[k]["90"], color: C.scBand } });
    return s;
  };
  const leg = (id) => Grafici.legend(id, [{ name: "Osservato", color: C.obs }]
    .concat(mod ? [{ name: "Base (mediana e 80%)", color: C.base, dash: true }, { name: "Con i parametri scelti (mediana e 80%)", color: C.sc }]
      : [{ name: "Previsione (mediana e 80%)", color: C.sc }]));
  const xTicks = (a, b) => { const out = []; let t = Math.ceil(a / 10800e3) * 10800e3; for (; t <= b; t += 10800e3) out.push(t); return out; };
  const comune = { xfmt: hhmm, xfmtTip: giornoOra, xTicks, vlines: [{ x: t0, label: "adesso" }] };
  leg("leg-presenti");
  Grafici.lineChart($("#ch-presenti"), { ...comune, series: serie("presenti"), yfmt: f0, height: 300,
    refs: [{ y: soglia, label: soglia + " postazioni" }], aria: "presenti osservati e previsti" });
  leg("leg-attesa");
  Grafici.lineChart($("#ch-attesa"), { ...comune, series: serie("in_attesa"), yfmt: f0, aria: "in attesa" });
  const ps = [{ name: mod ? "Base" : "Previsione", x: xs, y: r.base.prob_oltre[String(soglia)] || r.base.prob_oltre["83"], color: mod ? C.base : C.sc, dash: mod ? "5 4" : "" }];
  if (mod) ps.push({ name: "Con i parametri scelti", x: xs, y: r.scenario.prob_oltre["83"], color: C.sc });
  Grafici.legend("leg-prob", ps.map(s => ({ name: s.name, color: s.color, dash: !!s.dash })));
  Grafici.lineChart($("#ch-prob"), { ...comune, vlines: [], series: ps, yMin: 0, yMax: 1, yfmt: v => pct(v), aria: "probabilità sovraffollamento" });

  disegnaPrevCodice(r);
  // riquadri
  const u = STATO ? STATO.ultimo : null;
  const nowP = u ? Object.values(u.attesa).reduce((a, b) => a + b, 0) + Object.values(u.tratt).reduce((a, b) => a + b, 0) : null;
  const nowA = u ? Object.values(u.attesa).reduce((a, b) => a + b, 0) : null;
  const S = mod ? r.scenario : r.base;
  const k3 = S.ore.findIndex(h => h >= 3), kE = S.ore.length - 1;
  const maxProb = Math.max(...S.prob_oltre["83"]);
  $("#tiles-adesso").innerHTML = [
    ["Presenti adesso", f0(nowP), nowP ? `${pct(nowP / soglia)} delle ${soglia} postazioni` : ""],
    ["In attesa della visita", f0(nowA), ""],
    ["Presenti tra 3 ore", f0(S.presenti["50"][k3]), `80%: ${f0(S.presenti["10"][k3])}–${f0(S.presenti["90"][k3])}`],
    [`Presenti tra ${P.orizzonte} ore`, f0(S.presenti["50"][kE]), `80%: ${f0(S.presenti["10"][kE])}–${f0(S.presenti["90"][kE])}`],
    ["Oltre 83 postazioni", pct(maxProb), `probabilità massima nelle prossime ${P.orizzonte} h`],
  ].map(([k, v, d]) => `<div class="tile"><div class="k">${k}</div><div class="v">${v}</div><div class="d">${d}</div></div>`).join("");
}

let COD_ADESSO = 3;
function disegnaPrevCodice(r) {
  bottoniCodice($("#sel-cod-adesso"), COD_ADESSO, c => { COD_ADESSO = c; disegnaPrevCodice(ULTIMA_PREV); });
  const C = COL(), c = COD_ADESSO, t0 = new Date(r.inizio).getTime();
  const xs = r.base.ore.map(h => t0 + h * 3600e3);
  const hs = STATO ? STATO.storia.ts.map(t => new Date(t).getTime()) : [];
  const mod = r.modificato;
  const serie = (oss, chiave) => {
    const s = [{ name: "Osservato", x: hs, y: STATO ? STATO.storia.per_codice[c][oss] : [], color: C.obs }];
    s.push({ name: mod ? "Base" : "Previsione", x: xs, y: r.base[chiave][c]["50"], color: mod ? C.base : C.cat[c - 1], dash: mod ? "5 4" : "",
      band: { lo: r.base[chiave][c]["10"], hi: r.base[chiave][c]["90"], color: mod ? C.baseBand : C.scBand } });
    if (mod) s.push({ name: "Con i parametri scelti", x: xs, y: r.scenario[chiave][c]["50"], color: C.sc,
      band: { lo: r.scenario[chiave][c]["10"], hi: r.scenario[chiave][c]["90"], color: C.scBand } });
    return s;
  };
  const xTicks = (a, b) => { const out = []; let t = Math.ceil(a / 21600e3) * 21600e3; for (; t <= b; t += 21600e3) out.push(t); return out; };
  const comune = { xfmt: hhmm, xfmtTip: giornoOra, xTicks, vlines: [{ x: t0, label: "adesso" }], yfmt: f0, height: 220 };
  const sp = serie("presenti", "per_codice"), sa = serie("in_attesa", "attesa_codice");
  Grafici.legend("leg-cod-pres", sp.map(x => ({ name: x.name + (x.name === "Osservato" ? "" : " (presenti)"), color: x.color, dash: !!x.dash })));
  Grafici.lineChart($("#ch-cod-pres"), { ...comune, series: sp, aria: "presenti codice " + c });
  Grafici.legend("leg-cod-att", sa.map(x => ({ name: x.name + (x.name === "Osservato" ? "" : " (in attesa)"), color: x.color, dash: !!x.dash })));
  Grafici.lineChart($("#ch-cod-att"), { ...comune, series: sa, aria: "in attesa codice " + c });
}

/* ------------------------------------------------------------------ regime */
let REGIME_STALE = true, REQ_REG = 0;
async function aggiornaRegime() {
  const id = ++REQ_REG;
  REGIME_STALE = false;
  $("#tiles-regime").classList.add("caricamento");
  try {
    const r = await API("/api/regime", P);
    if (id !== REQ_REG) return;
    disegnaRegime(r);
  } catch (e) { $("#tiles-regime").innerHTML = `<p class="errore">${e.message}</p>`; }
  finally { if (id === REQ_REG) $("#tiles-regime").classList.remove("caricamento"); }
}

function delta(s, b, piuMeglio = false) {
  if (s == null || b == null || !b) return "";
  const d = s / b - 1;
  if (Math.abs(d) < 0.005) return "come la base";
  const meglio = piuMeglio ? d > 0 : d < 0;
  return `<span class="${meglio ? "meglio" : "peggio"}">${d > 0 ? "+" : "−"}${pct(Math.abs(d))}</span> vs base`;
}

let ULTIMO_REGIME = null;
$("#sel-metrica-cod").addEventListener("change", () => ULTIMO_REGIME && disegnaRegimeCodici(ULTIMO_REGIME));
function disegnaRegimeCodici(r) {
  const C = COL(), s = r.scenario, b = r.base, k = $("#sel-metrica-cod").value;
  const fmt = { permanenza_codice: v => f1(v) + " h", attesa_visita_codice: ore, p24_codice: v => pct(v, 1), p8_codice: v => pct(v, 1), presenti_codice: f1 }[k];
  const fonteReale = { permanenza_codice: "Reale ASL " + CFG.asl.anno, p24_codice: "Reale ASL " + CFG.asl.anno, p8_codice: "Reale ASL " + CFG.asl.anno,
    attesa_visita_codice: "Reale (presenze misurate)", presenti_codice: "Reale (presenze misurate)" }[k];
  const cods = [1, 2, 3, 4, 5];
  const bs = [{ name: fonteReale, color: C.obs, values: cods.map(c => r.reale[k] ? r.reale[k][c] : null) },
    { name: "Base", color: C.base, values: cods.map(c => b[k][c]) },
    { name: "Con i parametri scelti", color: C.sc, values: cods.map(c => s[k][c]) }];
  Grafici.legend("leg-codici", bs.map(x => ({ name: x.name, color: x.color, kind: "box" })));
  Grafici.barChart($("#ch-codici"), { cats: cods.map(c => "Codice " + c), series: bs, yfmt: fmt, aria: "indicatore per codice" });
  const R = r.reale;
  const righe = [
    ["Accessi/anno", "accessi_codice", f0, R.accessi_codice],
    ["Attesa prima visita", "attesa_visita_codice", ore, R.attesa_visita_codice],
    ["Permanenza media", "permanenza_codice", ore, R.permanenza_codice],
    ["Oltre 8 ore", "p8_codice", v => pct(v, 1), R.p8_codice],
    ["Oltre 24 ore", "p24_codice", v => pct(v, 1), R.p24_codice],
    ["Presenti medi", "presenti_codice", f1, R.presenti_codice],
    ["In attesa medi", "in_attesa_codice", f1, null],
    ["Ricoveri con boarding/anno", "boarding_n_codice", f0, null],
    ["Attesa del letto", "boarding_ore_codice", ore, null],
    ["Abbandoni", "abbandoni_codice", v => pct(v, 1), null],
  ];
  $("#tab-regime-cod").innerHTML = `<table><thead><tr><th>Indicatore</th>${cods.map(c => `<th>Codice ${c}</th>`).join("")}</tr></thead><tbody>` +
    righe.map(([n, key, f, re]) => `<tr><td>${n}<br><span class="nota">reale · base · scelti</span></td>` + cods.map(c => {
      const sv = s[key] ? s[key][c] : null, bv = b[key] ? b[key][c] : null;
      const d = sv != null && bv ? sv / bv - 1 : 0;
      const cls = Math.abs(d) < 0.02 || key === "accessi_codice" || key === "presenti_codice" ? "" : (d < 0 ? "meglio" : "peggio");
      return `<td><span class="nota">${re ? f(re[c]) : "—"}</span><br>${f(bv)}<br><b class="${cls}">${f(sv)}</b></td>`;
    }).join("") + "</tr>").join("") + `</tbody></table>
    <p class="nota">Reale: dati ASL ${CFG.asl.anno} (accessi, permanenze, oltre 8/24 ore) e presenze misurate riportate al carico ${CFG.asl.anno} (attese e presenti). In verde/rosso le variazioni oltre il 2% rispetto alla base.</p>`;
}

function disegnaRegime(r) {
  const C = COL(), s = r.scenario, b = r.base;
  const inst = !s.stabile ? `<p class="errore"><b>Attenzione:</b> con questi parametri le code non si stabilizzano (i letti liberi al giorno non bastano: margine ${f1(r.margine_letti_giorno)}/giorno). I valori medi non sono significativi.</p>` : "";
  const T = [
    ["Permanenza media", ore(s.permanenza), delta(s.permanenza, b.permanenza), "base " + ore(b.permanenza)],
    ["Attesa prima visita", ore(s.attesa_visita), delta(s.attesa_visita, b.attesa_visita), "base " + ore(b.attesa_visita)],
    ["Accessi oltre 24 h", pct(s.p24, 1), delta(s.p24, b.p24), "base " + pct(b.p24, 1)],
    ["Attesa letto (boarding)", ore(s.boarding_ore), delta(s.boarding_ore, b.boarding_ore), "base " + ore(b.boarding_ore)],
    ["Tempo oltre 83 presenti", pct(s.oltre_83), delta(s.oltre_83, b.oltre_83), "base " + pct(b.oltre_83)],
    ["Presenti medi", f0(s.presenti), delta(s.presenti, b.presenti), "base " + f0(b.presenti)],
    ["Costo annuo indicativo", r.costo.totale ? euro(r.costo.totale) : "0", r.costo.voci.map(v => v[0]).join(", ") || "nessuna modifica di risorse", ""],
  ];
  $("#tiles-regime").innerHTML = inst + T.map(([k, v, d, e]) =>
    `<div class="tile"><div class="k">${k}</div><div class="v">${v}</div><div class="d">${d}</div><div class="d">${e}</div></div>`).join("");
  $("#costo").innerHTML = `Costo annuo indicativo delle modifiche: <b>${euro(r.costo.totale)}</b>` +
    (r.costo.voci.length ? `<br><span class="nota">${r.costo.voci.map(v => v[0] + " " + euro(v[1])).join(" · ")}</span>` : "");
  const h = [...Array(24).keys()];
  const sr = [{ name: "Reale (presenze misurate)", x: h, y: r.reale.presenti_ora, color: C.obs },
    { name: "Base", x: h, y: b.presenti_ora, color: C.base, dash: "5 4" },
    { name: "Con i parametri scelti", x: h, y: s.presenti_ora, color: C.sc }];
  Grafici.legend("leg-ora", sr.map(x => ({ name: x.name, color: x.color, dash: !!x.dash })));
  Grafici.lineChart($("#ch-ora"), { series: sr, xfmt: v => v + ":00", yfmt: f0, xTicks: () => [0, 3, 6, 9, 12, 15, 18, 21],
    refs: [{ y: CFG.config.gemello.soglia_affollamento, label: "83 postazioni" }], aria: "presenti per ora" });
  ULTIMO_REGIME = r;
  disegnaRegimeCodici(r);
  const riga = (n, k, fmt, piu) => `<tr><td>${n}</td><td>${fmt(b[k])}</td><td>${fmt(s[k])}</td><td>${delta(s[k], b[k], piu).replace(" vs base", "")}</td></tr>`;
  $("#tab-regime-det").innerHTML = `<table><thead><tr><th>Indicatore</th><th>Base</th><th>Parametri scelti</th><th>Variazione</th></tr></thead><tbody>
    ${riga("Accessi/anno", "accessi", f0)}${riga("Permanenza media", "permanenza", ore)}${riga("Attesa prima visita", "attesa_visita", ore)}
    ${riga("Oltre 8 h", "p8", v => pct(v, 1))}${riga("Oltre 24 h", "p24", v => pct(v, 1))}${riga("Boarding/anno", "boarding_n", f0)}
    ${riga("Attesa letto", "boarding_ore", ore)}${riga("Abbandoni", "abbandoni", v => pct(v, 1))}${riga("Presenti medi", "presenti", f0)}
    ${riga("In attesa medi", "in_attesa", f1)}${riga("Tempo oltre 83 presenti", "oltre_83", v => pct(v))}</tbody></table>
    <p class="nota">Simulazione di ${CFG.config.gemello.regime.giorni} giorni × ${CFG.config.gemello.regime.repliche} repliche: differenze sotto 1-2 punti sono rumore statistico.</p>`;
}

/* ------------------------------------------------------------------ lavori lunghi */
async function lancia(tipo, body, progId, onDone, btn) {
  btn.disabled = true;
  const box = $(progId);
  box.innerHTML = `<div class="barra"><div></div></div><span>avvio…</span>`;
  if (STATICO) {
    const t0 = Date.now();
    try {
      const r = await Statico.lavoro(tipo, body, (x, msg) => {
        box.querySelector(".barra div").style.width = (100 * x) + "%";
        if (msg) box.querySelector("span").textContent = msg;
      });
      box.innerHTML = `<span>fatto in ${Math.round((Date.now() - t0) / 1000)} s (calcolato nel tuo browser)</span>`;
      onDone(r);
    } catch (e) { box.innerHTML = `<p class="errore">${e.message}</p>`; }
    btn.disabled = false;
    return;
  }
  try {
    const { id } = await API("/api/job/" + tipo, body);
    const poll = async () => {
      const j = await API("/api/job/" + id);
      box.querySelector(".barra div").style.width = (100 * (j.progresso || 0)) + "%";
      box.querySelector("span").textContent = j.messaggio || j.stato;
      if (j.stato === "in corso") return setTimeout(poll, 1500);
      btn.disabled = false;
      if (j.stato === "errore") { box.innerHTML = `<p class="errore">${j.errore}</p>`; return; }
      box.innerHTML = `<span>fatto in ${Math.round(j.durata)} s</span>`;
      onDone(j.risultato);
    };
    poll();
  } catch (e) { btn.disabled = false; box.innerHTML = `<p class="errore">${e.message}</p>`; }
}

$("#btn-ottimizza").addEventListener("click", e => lancia("ottimizza",
  { ...P, target: +$("#p-target").value / 100, metrica: $("#p-metrica").value }, "#prog-ottimizza", mostraOttimizza, e.target));

function mostraOttimizza(r) {
    const sing = r.singole.map(x => `<tr><td>${x.nome}</td><td>${x.effetto > 0 ? "−" : "+"}${pct(Math.abs(x.effetto), 1)}</td><td>${euro(x.costo)}</td>
      <td>${x.effetto > 0.001 ? euro(x.costo / (x.effetto * 100)) : "—"}</td><td>${ore(x.attesa)}</td><td>${pct(x.oltre_83)}</td></tr>`).join("");
    let cum = 0;
    const mix = r.passi.map((p, i) => { cum += p.costo; return `<tr><td>${i + 1}. ${p.leva}</td><td>−${pct(p.guadagno, 1)}</td><td>−${pct(p.cumulato, 1)}</td><td>${euro(p.costo)}</td><td>${(cum / 1e6).toLocaleString("it-IT", { maximumFractionDigits: 2 })} M€</td></tr>`; }).join("");
    const ok = r.raggiunto >= r.target - 1e-9;
    $("#ris-ottimizza").innerHTML = `
      <h3>Mix scelto ${ok ? "" : '<span class="errore">(obiettivo non raggiunto con le leve disponibili)</span>'}</h3>
      <table><thead><tr><th>Leva (in ordine di scelta)</th><th>Guadagno</th><th>Cumulato</th><th>Costo/anno</th><th>Costo cumulato</th></tr></thead><tbody>${mix}</tbody></table>
      <p>Risultato: ${r.metrica_nome} da ${(r.metrica === "presenti" ? f1 : ore)(r.valore_partenza)} a <b>${(r.metrica === "presenti" ? f1 : ore)(r.valore_finale)}</b> (−${pct(r.raggiunto, 1)}). Permanenza ${ore(r.partenza.permanenza)} → <b>${ore(r.finale.permanenza)}</b>,
      attesa visita ${ore(r.partenza.attesa_visita)} → <b>${ore(r.finale.attesa_visita)}</b>, oltre 24 h ${pct(r.partenza.p24, 1)} → ${pct(r.finale.p24, 1)},
      tempo oltre 83 presenti ${pct(r.partenza.oltre_83)} → ${pct(r.finale.oltre_83)}.</p>
      <h3>Ogni leva da sola (ordinate per costo per punto)</h3>
      <table><thead><tr><th>Leva</th><th>Effetto</th><th>Costo/anno</th><th>Costo per punto %</th><th>Attesa visita</th><th>Oltre 83</th></tr></thead><tbody>${sing}</tbody></table>`;
}


$("#btn-backtest").addEventListener("click", e => lancia("backtest",
  { ...P, giorni: +$("#p-bt-giorni").value, ogni_ore: +$("#p-bt-ogni").value }, "#prog-backtest", mostraBacktest, e.target));

function mostraBacktest(r) {
    const riga = (h, k) => {
      const v = [r.mae["gemello_" + k][h], r.mae["persist_" + k][h], r.mae["clim_" + k][h]];
      const mn = Math.min(...v.filter(x => x != null));
      return v.map(x => `<td class="${x === mn ? "meglio" : ""}">${f1(x)}</td>`).join("");
    };
    const rows = r.orizzonti.map(h => `<tr><td>+${h} h</td>${riga(h, "tot")}${riga(h, "att")}<td>${pct(r.copertura_80[h])}</td></tr>`).join("");
    $("#ris-backtest").innerHTML = `<p class="nota">${r.n_previsioni} previsioni dal ${new Date(r.periodo[0]).toLocaleDateString("it-IT")} al ${new Date(r.periodo[1]).toLocaleDateString("it-IT")}. Errore medio assoluto in persone (in verde il migliore).</p>
      <table><thead><tr><th>Orizzonte</th><th>Presenti: gemello</th><th>persistenza</th><th>media oraria</th><th>In attesa: gemello</th><th>persistenza</th><th>media oraria</th><th>Copertura fascia 80%</th></tr></thead><tbody>${rows}</tbody></table>
      <p class="nota">La copertura dovrebbe essere vicina all'80%: se è molto più bassa la forchetta è troppo stretta (aumenta <code>gemello.analoghi.allarga</code> in config.yaml).</p>`;
}


$("#btn-storica").addEventListener("click", e => lancia("validazione_storica", P, "#prog-storica", mostraStorica, e.target));

function mostraStorica(r) {
  const rows = r.righe.map(x => `<tr><td>${x.anno}</td><td>${f0(x.accessi)}</td><td>${f1(x.permanenza_reale)} h</td><td>${f1(x.permanenza_sim)} h</td>` +
    [1, 2, 3, 4, 5].map(c => `<td>${f1(x.codici[c].reale)} / ${f1(x.codici[c].sim)}</td>`).join("") +
    `<td>${x.boarding_reale == null ? "—" : f1(x.boarding_reale)} / ${f1(x.boarding_sim)}</td></tr>`).join("");
  $("#ris-storica").innerHTML = `<table><thead><tr><th>Anno</th><th>Accessi</th><th>Permanenza reale</th><th>simulata</th>
    ${[1, 2, 3, 4, 5].map(c => `<th>Cod. ${c} reale / sim.</th>`).join("")}<th>Boarding h reale / sim.</th></tr></thead><tbody>${rows}</tbody></table>`;
}


$("#btn-calibra").addEventListener("click", e => lancia("calibra",
  { turni: $("#p-cal-turni").value, rivalutazione_precedenza: $("#p-cal-rivprec").checked, anno: +$("#p-cal-anno").value },
  "#prog-calibra", async r => {
    const v = r.validazione;
    $("#ris-calibra").innerHTML = `<p>Salvato <code>${r.file}</code>. Permanenza ${f1(v.permanenza[0])} h (reale ${f1(v.permanenza[1])}),
      in attesa ${f1(v.in_attesa[0])} (${f1(v.in_attesa[1])}), boarding ${f1(v.boarding_ore[0])} h (${f1(v.boarding_ore[1])}),
      correlazione oraria presenti ${f1(v.corr_presenti_ora)}, in attesa ${f1(v.corr_attesa_ora)}.</p>`;
    CFG = await API("/api/config"); disegnaParametri(); cambiato();
  }, e.target));

$("#btn-ricarica").addEventListener("click", async () => {
  const r = await API("/api/ricarica", {}); alert("Dati ricaricati fino a " + r.presenze_fino_a); aggiornaStato();
});

/* ------------------------------------------------------------------ storico */
let STORICO = null;
async function caricaStorico() {
  STORICO = await API("/api/storico");
  const C = COL(), S = STORICO.serie, anni = Object.keys(S).map(Number);
  // il 2021 (pandemia) resta marcato ma fuori dalle linee: altrimenti schiaccia la scala
  const linee = (fn) => [1, 2, 3, 4, 5].map((c, i) => ({ name: "Codice " + c, x: anni, y: anni.map(a => S[a].anomalo ? null : fn(S[a], c)), color: C.cat[i] }));
  const leg = id => Grafici.legend(id, [1, 2, 3, 4, 5].map((c, i) => ({ name: NOMI_COD[c], color: C.cat[i] })));
  const comune = { xfmt: v => String(v), xTicks: () => anni, punti: true, vlines: [{ x: 2021, label: "2021 escluso (pandemia)" }] };
  leg("leg-st-perm"); Grafici.lineChart($("#ch-st-perm"), { ...comune, series: linee((s, c) => s.permanenza[c]), yfmt: f0 });
  leg("leg-st-acc"); Grafici.lineChart($("#ch-st-acc"), { ...comune, series: linee((s, c) => s.accessi[c]), yfmt: f0 });
  leg("leg-st-rap"); Grafici.lineChart($("#ch-st-rap"), { ...comune, series: linee((s, c) => s.rapporto_media[c]), yfmt: v => f1(v) + "×" });
  leg("leg-st-24"); Grafici.lineChart($("#ch-st-24"), { ...comune, series: linee((s, c) => s.p24[c]), yfmt: v => pct(v) });
  $("#tab-crescita").innerHTML = `<table><thead><tr>${[1, 2, 3, 4, 5].map(c => `<th>${NOMI_COD[c]}</th>`).join("")}<th>Totale</th></tr></thead>
    <tbody><tr>${[1, 2, 3, 4, 5].map(c => `<td>${(STORICO.crescita[c] >= 0 ? "+" : "") + pct(STORICO.crescita[c], 1)}</td>`).join("")}<td>+${pct(STORICO.crescita_totale, 1)}</td></tr></tbody></table>
    <p class="nota">La crescita è concentrata nei codici 4-5 (permanenze brevi): i ricoveri crescono molto meno degli accessi.</p>`;
  $("#tab-storico-det").innerHTML = `<table><thead><tr><th>Anno</th><th>Accessi</th><th>Permanenza media</th><th>Presenti (Little)</th><th>Boarding</th><th>Attesa letto</th><th>Abbandoni</th></tr></thead><tbody>` +
    anni.map(a => `<tr><td>${a}${S[a].anomalo ? " *" : ""}</td><td>${f0(S[a].totale)}</td><td>${ore(S[a].permanenza_media)}</td><td>${f0(S[a].presenti_little)}</td>
    <td>${f0(S[a].boarding_n)}</td><td>${ore(S[a].boarding_ore)}</td><td>${S[a].abbandoni_quota == null ? "—" : pct(S[a].abbandoni_quota, 1)}</td></tr>`).join("") + "</tbody></table>";
}

/* ------------------------------------------------------------------ versione online */
async function mostraPubblicati() {
  try {
    const a = await Statico.json("dati/affidabilita.json");
    mostraBacktest(a.backtest);
    mostraStorica({ righe: a.storica });
    $("#prog-backtest").innerHTML = `<span>Test calcolato in locale il ${new Date(a.calcolato).toLocaleString("it-IT")} sullo scenario di riferimento.</span>`;
    $("#prog-storica").innerHTML = `<span>Risultato pubblicato (scenario di riferimento). Puoi rifarlo con i tuoi parametri: «Esegui».</span>`;
  } catch (e) { /* niente dati pubblicati */ }
  if (CFG.report && CFG.report.length) {
    $("#report-pubblicati").innerHTML = "Report completi calcolati in locale: " + CFG.report.map(r =>
      `<a href="dati/${r}.html" target="_blank">${r.replace("report_", "").replace(/_/g, " ")}</a>`).join(" · ");
  }
}

/* ------------------------------------------------------------------ esportazione */
function parametriModificati() {
  const d = parametriDefault(), out = [];
  const nomi = Object.fromEntries(SLIDERS.map(s => [s.id, s]));
  if (P.turni !== d.turni) out.push(["Turni medici", P.turni]);
  if (P.rivalutazione_precedenza !== d.rivalutazione_precedenza) out.push(["Rivalutazione con precedenza", P.rivalutazione_precedenza ? "sì" : "no"]);
  Object.keys(P.medici).forEach(f => { if (P.medici[f] !== CFG.config.turni_medici[P.turni][f]) out.push(["Medici fascia " + f, `${CFG.config.turni_medici[P.turni][f]} → ${P.medici[f]}`]); });
  SLIDERS.forEach(s => { if (P[s.id] !== s.def) out.push([s.lbl, s.fmt(P[s.id])]); });
  [1, 2, 3, 4, 5].forEach(c => SLIDERS_COD.forEach(s => { if (P.per_codice[c][s.k] !== s.def) out.push([`Codice ${c}: ${s.lbl}`, s.fmt(P.per_codice[c][s.k])]); }));
  if (P.letti_seguono_ricoveri) out.push(["Letti che crescono con i ricoveri", "sì"]);
  P.leve.forEach(id => { const l = CFG.leve.find(x => x.id === id); if (l) out.push(["Leva", l.nome]); });
  return out;
}
function scarica(nome, testo, tipo) {
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([testo], { type: tipo }));
  a.download = nome; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
}
const nomeFile = est => "simulazione-ps-prato-" + new Date().toISOString().slice(0, 16).replace(/[:T]/g, "-") + "." + est;

async function assicuraRegime() { if (REGIME_STALE || !ULTIMO_REGIME) await aggiornaRegime(); return ULTIMO_REGIME; }

$("#btn-json").addEventListener("click", async e => {
  e.target.disabled = true;
  try {
    const r = await assicuraRegime();
    const out = {
      strumento: "Gemello digitale del PS Santo Stefano di Prato — pspratolive.it",
      generato: new Date().toISOString(),
      versione: STATICO ? "online (simulazione nel browser)" : "locale",
      dati: { asl: `ASL Toscana Centro, accesso civico prot. 158918/2026, anno ${CFG.asl.anno}`, presenze: CFG.presenze },
      scenario_calibrato: P.turni + (P.rivalutazione_precedenza ? "_rivprec" : ""),
      parametri: P,
      parametri_modificati: Object.fromEntries(parametriModificati()),
      costo_annuo_indicativo: r.costo,
      regime_annuo: { base: r.base, con_parametri: r.scenario, reale: r.reale },
      previsione_prossime_ore: ULTIMA_PREV ? { inizio: ULTIMA_PREV.inizio, ore: ULTIMA_PREV.base.ore, base: ULTIMA_PREV.base,
        con_parametri: ULTIMA_PREV.modificato ? ULTIMA_PREV.scenario : null } : null,
      avvertenze: ["Risultati di un modello di simulazione tarato sui dati ASL e sulle presenze misurate: non sono misure.",
        "Costi ed effetti di alcune leve sono stime indicative (vedi metodo).",
        "Differenze sotto 1-2 punti percentuali sono rumore statistico."],
    };
    scarica(nomeFile("json"), JSON.stringify(out, null, 1), "application/json");
  } finally { e.target.disabled = false; }
});

$("#btn-pdf").addEventListener("click", async e => {
  e.target.disabled = true;
  try {
    const r = await assicuraRegime(), b = r.base, s = r.scenario, mod = parametriModificati();
    // grafici ridisegnati a larghezza fissa fuori schermo
    const box = document.createElement("div");
    box.style.cssText = "position:absolute;left:-10000px;top:0;width:820px";
    document.body.appendChild(box);
    const svg = (fn) => { const d = document.createElement("div"); d.className = "chart"; d.style.width = "820px"; box.appendChild(d); fn(d); return d.innerHTML; };
    const C = COL(), h = [...Array(24).keys()];
    const gOra = svg(d => Grafici.lineChart(d, { series: [
      { name: "Reale", x: h, y: r.reale.presenti_ora, color: C.obs }, { name: "Base", x: h, y: b.presenti_ora, color: C.base, dash: "5 4" },
      { name: "Con i parametri scelti", x: h, y: s.presenti_ora, color: C.sc }], xfmt: v => v + ":00", yfmt: f0,
      xTicks: () => [0, 3, 6, 9, 12, 15, 18, 21], refs: [{ y: 83, label: "83 postazioni" }], height: 240 }));
    const gCod = svg(d => Grafici.barChart(d, { cats: [1, 2, 3, 4, 5].map(c => "Codice " + c), series: [
      { name: "Reale ASL", color: C.obs, values: [1, 2, 3, 4, 5].map(c => r.reale.permanenza_codice[c]) },
      { name: "Base", color: C.base, values: [1, 2, 3, 4, 5].map(c => b.permanenza_codice[c]) },
      { name: "Con i parametri scelti", color: C.sc, values: [1, 2, 3, 4, 5].map(c => s.permanenza_codice[c]) }], yfmt: v => f1(v) + " h", height: 220 }));
    let gPrev = "";
    if (ULTIMA_PREV) {
      const t0 = new Date(ULTIMA_PREV.inizio).getTime(), xs = ULTIMA_PREV.base.ore.map(x => t0 + x * 3600e3);
      const ser = [{ name: "Previsione base", x: xs, y: ULTIMA_PREV.base.presenti["50"], color: C.base, dash: ULTIMA_PREV.modificato ? "5 4" : "",
        band: { lo: ULTIMA_PREV.base.presenti["10"], hi: ULTIMA_PREV.base.presenti["90"], color: C.baseBand } }];
      if (ULTIMA_PREV.modificato) ser.push({ name: "Con i parametri", x: xs, y: ULTIMA_PREV.scenario.presenti["50"], color: C.sc,
        band: { lo: ULTIMA_PREV.scenario.presenti["10"], hi: ULTIMA_PREV.scenario.presenti["90"], color: C.scBand } });
      gPrev = svg(d => Grafici.lineChart(d, { series: ser, xfmt: hhmm, refs: [{ y: 83, label: "83 postazioni" }], yfmt: f0, height: 220,
        xTicks: (a, z) => { const o = []; for (let t = Math.ceil(a / 10800e3) * 10800e3; t <= z; t += 10800e3) o.push(t); return o; } }));
    }
    box.remove();
    const riga = (n, k, f) => `<tr><td>${n}</td><td>${f(b[k])}</td><td><b>${f(s[k])}</b></td><td>${delta(s[k], b[k]).replace(" vs base", "")}</td></tr>`;
    const cod = [1, 2, 3, 4, 5];
    const rc = (n, k, f, re) => `<tr><td>${n}</td>${cod.map(c => `<td>${re ? f(re[c]) + " · " : ""}${f(b[k][c])} · <b>${f(s[k][c])}</b></td>`).join("")}</tr>`;
    const html = `<!DOCTYPE html><html lang="it" data-theme="light"><head><meta charset="utf-8"><title>Simulazione PS Prato</title>
      <link rel="stylesheet" href="${new URL("../../assets/sito.css", location.href)}">
      <link rel="stylesheet" href="${new URL("style.css", location.href)}">
      <style>body{background:#fff;padding:24px 32px;max-width:900px;margin:0 auto} h1{font-size:20px} h2{font-size:15px;margin:18px 0 6px}
      table{margin:6px 0 10px} td,th{padding:3px 6px;font-size:11.5px} .chart svg{width:100%} .meta{color:#555;font-size:12px}
      @page{size:A4;margin:14mm} @media print{.noprint{display:none}} .avv{font-size:11px;color:#555;border-top:1px solid #ddd;padding-top:8px;margin-top:16px}</style></head>
      <body class="viz-root"><p class="noprint"><button onclick="print()">Stampa / salva in PDF</button></p>
      <div class="brand"><svg class="brandmark" viewBox="0 0 64 64"><rect x="2" y="2" width="60" height="60" rx="14" fill="#e11d2a"/><rect x="26.5" y="12" width="11" height="40" rx="3.5" fill="#fff"/><rect x="12" y="26.5" width="40" height="11" rx="3.5" fill="#fff"/></svg>
      <div><div class="brandname">PS Prato <span class="live">Live</span></div><div class="brandtag">Simulatore del Pronto Soccorso</div></div></div>
      <h1>Simulazione del Pronto Soccorso Santo Stefano di Prato</h1>
      <p class="meta">Generata il ${new Date().toLocaleString("it-IT")} con il gemello digitale di pspratolive.it · scenario calibrato ${P.turni}${P.rivalutazione_precedenza ? " (rivalutazione con precedenza)" : ""} · dati ASL ${CFG.asl.anno} (accesso civico prot. 158918/2026) e presenze ${new Date(CFG.presenze.inizio).toLocaleDateString("it-IT")}–${new Date(CFG.presenze.fine).toLocaleDateString("it-IT")}</p>
      <h2>Parametri modificati</h2>
      ${mod.length ? `<table><tbody>${mod.map(([k, v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join("")}</tbody></table>` : "<p>Nessuno: situazione attuale simulata.</p>"}
      <p>Costo annuo indicativo delle modifiche: <b>${euro(r.costo.totale)}</b>${r.costo.voci.length ? " (" + r.costo.voci.map(v => v[0] + " " + euro(v[1])).join("; ") + ")" : ""}</p>
      ${!s.stabile ? '<p class="errore"><b>Attenzione:</b> con questi parametri le code non si stabilizzano; le medie non sono significative.</p>' : ""}
      <h2>Risultati in media su un anno</h2>
      <table><thead><tr><th>Indicatore</th><th>Base</th><th>Con i parametri</th><th>Variazione</th></tr></thead><tbody>
      ${riga("Accessi/anno", "accessi", f0)}${riga("Permanenza media", "permanenza", ore)}${riga("Attesa prima visita", "attesa_visita", ore)}
      ${riga("Oltre 8 ore", "p8", v => pct(v, 1))}${riga("Oltre 24 ore", "p24", v => pct(v, 1))}${riga("Attesa del letto (boarding)", "boarding_ore", ore)}
      ${riga("Abbandoni", "abbandoni", v => pct(v, 1))}${riga("Presenti medi", "presenti", f0)}${riga("Tempo oltre 83 presenti", "oltre_83", v => pct(v))}</tbody></table>
      <h2>Per codice di triage <span class="meta">(reale · base · <b>con i parametri</b>)</span></h2>
      <table><thead><tr><th></th>${cod.map(c => `<th>Codice ${c}</th>`).join("")}</tr></thead><tbody>
      ${rc("Permanenza", "permanenza_codice", ore, r.reale.permanenza_codice)}${rc("Attesa visita", "attesa_visita_codice", ore, r.reale.attesa_visita_codice)}
      ${rc("Oltre 24 ore", "p24_codice", v => pct(v, 1), r.reale.p24_codice)}${rc("Presenti medi", "presenti_codice", f1, r.reale.presenti_codice)}</tbody></table>
      <h2>Presenti medi per ora del giorno</h2><div class="chart">${gOra}</div>
      <h2>Permanenza media per codice</h2><div class="chart">${gCod}</div>
      ${gPrev ? `<h2>Previsione delle prossime ore (da ${new Date(ULTIMA_PREV.inizio).toLocaleString("it-IT")})</h2><div class="chart">${gPrev}</div>` : ""}
      <p class="avv">Risultati di un modello di simulazione tarato sui dati ufficiali ASL e sulle presenze misurate ogni 15 minuti: non sono misure.
      Costi ed effetti di alcune leve sono stime indicative. Differenze sotto 1-2 punti percentuali sono rumore statistico.
      Metodo: ${new URL("#metodo", location.href.split("#")[0])}</p></body></html>`;
    const w = window.open("", "_blank");
    if (!w) { alert("Il browser ha bloccato la finestra: consenti i pop-up per questo sito."); return; }
    w.document.write(html); w.document.close();
    setTimeout(() => { try { w.focus(); w.print(); } catch (err) { /* l'utente può usare il pulsante */ } }, 600);
  } finally { e.target.disabled = false; }
});

/* ------------------------------------------------------------------ avvio */
(async function () {
  try {
    const r = await fetch("/api/config", { cache: "no-store" });
    STATICO = !r.ok || !(r.headers.get("content-type") || "").includes("json");
  } catch (e) { STATICO = true; }
  if (STATICO) {
    document.body.classList.add("statico");
    await Statico.init();
    $("#p-orizzonte").querySelectorAll("option").forEach(o => { if (+o.value > 12) o.remove(); });
  }
  if (!STATICO) document.querySelectorAll("[data-sito]").forEach(a =>
    a.href = new URL(a.getAttribute("href"), "https://pspratolive.it/gemello/ui/").href);
  CFG = await API("/api/config");
  P = parametriDefault();
  $("#p-target").value = Math.round(CFG.config.target_riduzione * 100);
  $("#p-metrica").innerHTML = Object.entries(CFG.metriche).map(([k, v]) => `<option value="${k}">${v}</option>`).join("");
  $("#p-metrica").value = CFG.config.metrica_target;
  $("#p-bt-giorni").value = CFG.config.gemello.backtest.giorni;
  $("#p-bt-ogni").value = CFG.config.gemello.backtest.ogni_ore;
  $("#p-cal-anno").innerHTML = CFG.anni_asl.filter(a => a !== 2021).map(a => `<option ${a === CFG.asl.anno ? "selected" : ""}>${a}</option>`).join("");
  $("#p-orizzonte").value = String(CFG.config.gemello.orizzonte_ore);
  P.orizzonte = CFG.config.gemello.orizzonte_ore; $("#oriz-lbl").textContent = P.orizzonte;
  disegnaParametri();
  await aggiornaStato();
  setInterval(aggiornaStato, 60e3);
  window.addEventListener("resize", () => { if (ULTIMA_PREV) disegnaPrevisione(ULTIMA_PREV); });
  if (STATICO) mostraPubblicati();
  const h = location.hash.slice(1);
  vaiA(["regime", "investire", "storico", "affidabilita", "istruzioni", "metodo"].includes(h) ? h : "adesso");
  window.addEventListener("hashchange", () => { const t = location.hash.slice(1); if (document.getElementById("tab-" + t)) vaiA(t); });
})();
