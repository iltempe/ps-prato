/* Grafici SVG minimi, senza dipendenze: linee con fascia + barre raggruppate.
   Linee 2px, griglia hairline, mirino con tooltip, linee di riferimento etichettate. */
(function () {
  const NS = "http://www.w3.org/2000/svg";
  const tip = () => document.getElementById("tooltip");
  function el(tag, attrs, parent) {
    const e = document.createElementNS(NS, tag);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(e);
    return e;
  }
  function niceTicks(min, max, n) {
    const span = max - min || 1;
    const step0 = span / n, mag = Math.pow(10, Math.floor(Math.log10(step0)));
    const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(s => span / s <= n) || 10 * mag;
    const out = [];
    for (let v = Math.ceil(min / step) * step; v <= max + 1e-9; v += step) out.push(+v.toFixed(10));
    return out;
  }
  function showTip(evt, html) {
    const t = tip();
    t.innerHTML = html; t.style.display = "block";
    const w = t.offsetWidth, h = t.offsetHeight;
    let x = evt.clientX + 14, y = evt.clientY - h - 10;
    if (x + w > window.innerWidth - 8) x = evt.clientX - w - 14;
    if (y < 8) y = evt.clientY + 16;
    t.style.left = x + "px"; t.style.top = y + "px";
  }
  function hideTip() { tip().style.display = "none"; }
  function legend(id, items) {
    const box = document.getElementById(id);
    if (!box) return;
    box.innerHTML = items.map(it =>
      `<span><i class="${it.kind || ""}" style="background:${it.color}${it.dash ? ";background:repeating-linear-gradient(90deg," + it.color + " 0 4px,transparent 4px 7px)" : ""}"></i>${it.name}</span>`).join("");
  }

  /* opt: {series:[{name,x:[],y:[],color,width,dash,band:{lo:[],hi:[],color}}], refs:[{y,label}],
           vlines:[{x,label}], xfmt, yfmt, height, yMin, yMax, xTicks} */
  function lineChart(container, opt) {
    const W = Math.max(320, container.clientWidth), H = opt.height || 260;
    const m = { l: 44, r: 16, t: 14, b: 28 };
    container.innerHTML = "";
    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": opt.aria || "grafico" }, container);
    let xs = [], ys = [];
    opt.series.forEach(s => {
      xs = xs.concat(s.x);
      ys = ys.concat(s.y.filter(v => v != null));
      if (s.band) ys = ys.concat(s.band.lo, s.band.hi);
    });
    (opt.refs || []).forEach(r => ys.push(r.y));
    const x0 = Math.min(...xs), x1 = Math.max(...xs);
    let y0 = opt.yMin != null ? opt.yMin : Math.min(0, ...ys), y1 = opt.yMax != null ? opt.yMax : Math.max(...ys) * 1.06;
    if (y1 <= y0) y1 = y0 + 1;
    const sx = v => m.l + (v - x0) / (x1 - x0 || 1) * (W - m.l - m.r);
    const sy = v => H - m.b - (v - y0) / (y1 - y0) * (H - m.t - m.b);
    const g = el("g", { class: "grid" }, svg);
    const yt = niceTicks(y0, y1, 5);
    yt.forEach(v => {
      el("line", { x1: m.l, x2: W - m.r, y1: sy(v), y2: sy(v) }, g);
      const t = el("text", { x: m.l - 6, y: sy(v) + 4, "text-anchor": "end" }, svg);
      t.textContent = (opt.yfmt || (v => v))(v);
    });
    const xt = opt.xTicks ? opt.xTicks(x0, x1) : niceTicks(x0, x1, 6);
    xt.forEach(v => {
      const t = el("text", { x: sx(v), y: H - 8, "text-anchor": "middle" }, svg);
      t.textContent = (opt.xfmt || (v => v))(v);
    });
    el("line", { x1: m.l, x2: W - m.r, y1: H - m.b, y2: H - m.b, stroke: "var(--axis)" }, svg);
    (opt.vlines || []).forEach(v => {
      const gg = el("g", { class: "ora" }, svg);
      el("line", { x1: sx(v.x), x2: sx(v.x), y1: m.t, y2: H - m.b }, gg);
      const t = el("text", { x: sx(v.x) + 4, y: m.t + 10 }, gg); t.textContent = v.label;
    });
    opt.series.forEach(s => {
      if (!s.band) return;
      let d = "";
      s.x.forEach((x, i) => { d += (i ? "L" : "M") + sx(x) + "," + sy(s.band.hi[i]); });
      for (let i = s.x.length - 1; i >= 0; i--) d += "L" + sx(s.x[i]) + "," + sy(s.band.lo[i]);
      el("path", { d: d + "Z", fill: s.band.color, stroke: "none" }, svg);
    });
    (opt.refs || []).forEach(r => {
      const gg = el("g", { class: "ref" }, svg);
      el("line", { x1: m.l, x2: W - m.r, y1: sy(r.y), y2: sy(r.y) }, gg);
      const t = el("text", { x: W - m.r - 2, y: sy(r.y) - 4, "text-anchor": "end" }, gg); t.textContent = r.label;
    });
    opt.series.forEach(s => {
      let d = "", pen = false;
      s.x.forEach((x, i) => {
        if (s.y[i] == null) { pen = false; return; }
        d += (pen ? "L" : "M") + sx(x) + "," + sy(s.y[i]); pen = true;
      });
      el("path", { d, fill: "none", stroke: s.color, "stroke-width": s.width || 2,
        "stroke-dasharray": s.dash || "", "stroke-linejoin": "round", "stroke-linecap": "round" }, svg);
      if (opt.punti) s.x.forEach((x, i) => { if (s.y[i] != null)
        el("circle", { cx: sx(x), cy: sy(s.y[i]), r: 4, fill: s.color, stroke: "var(--surface-1)", "stroke-width": 2 }, svg); });
    });
    // mirino
    const cross = el("g", { class: "cross", style: "display:none" }, svg);
    const cl = el("line", { y1: m.t, y2: H - m.b }, cross);
    const dots = opt.series.map(s => el("circle", { r: 4, fill: s.color, stroke: "var(--surface-1)", "stroke-width": 2 }, cross));
    const hit = el("rect", { x: m.l, y: 0, width: W - m.l - m.r, height: H, fill: "transparent" }, svg);
    hit.addEventListener("mousemove", evt => {
      const r = svg.getBoundingClientRect();
      const px = (evt.clientX - r.left) * W / r.width;
      const xv = x0 + (px - m.l) / (W - m.l - m.r) * (x1 - x0);
      cross.style.display = ""; cl.setAttribute("x1", sx(xv)); cl.setAttribute("x2", sx(xv));
      let rows = "";
      opt.series.forEach((s, k) => {
        let best = -1, bd = Infinity;
        s.x.forEach((x, i) => { const dd = Math.abs(x - xv); if (dd < bd && s.y[i] != null) { bd = dd; best = i; } });
        const tol = (x1 - x0) / 40;
        if (best < 0 || bd > tol) { dots[k].style.display = "none"; return; }
        dots[k].style.display = ""; dots[k].setAttribute("cx", sx(s.x[best])); dots[k].setAttribute("cy", sy(s.y[best]));
        const f = opt.yfmt || (v => v);
        const band = s.band ? ` <span style="color:var(--text-muted)">(${f(s.band.lo[best])}–${f(s.band.hi[best])})</span>` : "";
        rows += `<div class="r"><span><i style="background:${s.color}"></i>${s.name}</span><b>${f(s.y[best])}</b>${band}</div>`;
      });
      showTip(evt, `<div class="t">${(opt.xfmtTip || opt.xfmt || (v => v))(xv)}</div>${rows}`);
    });
    hit.addEventListener("mouseleave", () => { cross.style.display = "none"; hideTip(); });
  }

  /* opt: {cats:[], series:[{name,color,values:[]}], yfmt, height} */
  function barChart(container, opt) {
    const W = Math.max(320, container.clientWidth), H = opt.height || 240;
    const m = { l: 44, r: 10, t: 12, b: 30 };
    container.innerHTML = "";
    const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": opt.aria || "grafico a barre" }, container);
    const all = opt.series.flatMap(s => s.values).filter(v => v != null);
    const y1 = Math.max(...all) * 1.08 || 1;
    const sy = v => H - m.b - v / y1 * (H - m.t - m.b);
    niceTicks(0, y1, 5).forEach(v => {
      el("line", { x1: m.l, x2: W - m.r, y1: sy(v), y2: sy(v), stroke: "var(--grid)" }, svg);
      const t = el("text", { x: m.l - 6, y: sy(v) + 4, "text-anchor": "end" }, svg); t.textContent = (opt.yfmt || (v => v))(v);
    });
    const gw = (W - m.l - m.r) / opt.cats.length, ns = opt.series.length;
    const bw = Math.min(28, (gw * 0.7 - 2 * (ns - 1)) / ns);
    opt.cats.forEach((c, i) => {
      const gx = m.l + i * gw + (gw - (bw * ns + 2 * (ns - 1))) / 2;
      const t = el("text", { x: m.l + i * gw + gw / 2, y: H - 10, "text-anchor": "middle" }, svg); t.textContent = c;
      opt.series.forEach((s, k) => {
        const v = s.values[i]; if (v == null) return;
        const x = gx + k * (bw + 2), y = sy(v), h = H - m.b - y, r = Math.min(4, h, bw / 2);
        const d = `M${x},${H - m.b}V${y + r}Q${x},${y} ${x + r},${y}H${x + bw - r}Q${x + bw},${y} ${x + bw},${y + r}V${H - m.b}Z`;
        const p = el("path", { d, fill: s.color }, svg);
        const hit = el("rect", { x: x - 1, y: m.t, width: bw + 2, height: H - m.t - m.b, fill: "transparent" }, svg);
        hit.addEventListener("mousemove", evt => showTip(evt,
          `<div class="t">${c}</div>` + opt.series.map(ss => `<div class="r"><span><i style="background:${ss.color}"></i>${ss.name}</span><b>${(opt.yfmt || (v => v))(ss.values[i])}</b></div>`).join("")));
        hit.addEventListener("mouseleave", hideTip);
      });
    });
    el("line", { x1: m.l, x2: W - m.r, y1: H - m.b, y2: H - m.b, stroke: "var(--axis)" }, svg);
  }
  window.Grafici = { lineChart, barChart, legend };
})();
