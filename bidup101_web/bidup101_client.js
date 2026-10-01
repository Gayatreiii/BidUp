(() => {
"use strict";
const API = "/api/bidup101";
const $ = (s, r = document) => r.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const inr = n => "₹" + Number(n).toLocaleString("en-IN", { maximumFractionDigits: 0 });
const pct = (n, d = 1) => (n == null ? "–" : (n >= 0 ? "+" : "") + n.toFixed(d) + "%");
const cls = n => (n >= 0 ? "pos" : "neg");
const load = (k, d) => { try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : d; } catch { return d; } };
const save = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} };

const S = { portfolios: load("bidup101_portfolios", {}), active: load("bidup101_active", null),
  chat: [], alerts: load("bidup101_alerts", []), seen: new Set(load("bidup101_seen", [])), notifyOn: load("bidup101_notify", true),
  universe: null, chart: null };
const holdings = () => (S.portfolios[S.active] || []);
const persist = () => { save("bidup101_portfolios", S.portfolios); save("bidup101_active", S.active); };

async function api(path, body) {
  const res = await fetch(API + path, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {});
  let data = null; try { data = await res.json(); } catch {}
  if (!res.ok) throw new Error((data && data.detail) || `Request failed (${res.status})`);
  return data;
}
function ago(iso) {
  if (!iso) return "Recently";
  const m = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (isNaN(m)) return "Recently";
  if (m < 1) return "just now"; if (m < 60) return m + "m ago"; if (m < 1440) return Math.round(m / 60) + "h ago";
  return Math.round(m / 1440) + "d ago";
}
const priceLabel = iso => iso ? `Prices as of ${new Date(iso).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })} (${ago(iso)}) · delayed ~15 min, not real-time` : "Price time unavailable";
const spin = t => `<div class="card small">${t || "Loading…"}</div>`;
const errBox = e => `<div class="err">${esc(e.message || e)}</div>`;
const bars = w => Object.entries(w).sort((a, b) => b[1] - a[1]).map(([k, v]) =>
  `<div class="bar-row"><span>${esc(k)}</span><div class="bar"><i style="width:${(v * 100).toFixed(1)}%"></i></div><b>${(v * 100).toFixed(1)}%</b></div>`).join("");
const alertsHtml = r => (r.alerts || []).length
  ? r.alerts.map(a => `<div class="alert ${a.level}"><b>${a.level}</b> · ${esc(a.text)}</div>`).join("")
  : `<div class="ok">No elevated cross-sector risk signals right now.</div>`;
const disclosure = r => `<p class="small">${esc(r.disclosure || "")}</p>` + ((r.uncovered_weight || 0) > 0.05 ? `<p class="small">${(r.uncovered_weight * 100).toFixed(0)}% of your portfolio is in sectors the risk model does not cover, so it is not reflected in the alerts above.</p>` : "");

function reveal() {
  const els = document.querySelectorAll(".reveal:not(.in)");
  if (!("IntersectionObserver" in window)) return els.forEach(e => e.classList.add("in"));
  const io = new IntersectionObserver(es => es.forEach(en => { if (en.isIntersecting) { en.target.classList.add("in"); io.unobserve(en.target); } }), { threshold: .08 });
  els.forEach(e => io.observe(e));
}
function toast(t) { const d = document.createElement("div"); d.className = "toast"; d.textContent = t; $("#bidup101-toasts").append(d); setTimeout(() => d.remove(), 6000); }

/* ---------- chat ---------- */
const chips = ["Explain my portfolio health", "Which sector am I most exposed to?", "What does HHI mean?", "Should I buy TCS right now?"];
function chatBox(id, big) {
  return `<div class="card"><div id="${id}-log" class="chat ${big ? "big" : ""}"></div>
  <div class="chips">${chips.map(c => `<button class="chip" data-chip="${esc(c)}">${esc(c)}</button>`).join("")}</div>
  <div class="row"><input id="${id}-in" placeholder="Ask about your portfolio, indicators or risk signals…" maxlength="1500"><button class="btn" id="${id}-send">Send</button></div>
  <p class="small">Educational assistant — describes data, never tells you what to buy or sell.</p></div>`;
}
function bindChat(id) {
  const log = $(`#${id}-log`), inp = $(`#${id}-in`);
  const draw = () => { log.innerHTML = S.chat.length ? S.chat.map(m => `<div class="msg ${m.role === "user" ? "user" : m.err ? "err" : "bot"}">${esc(m.content)}</div>`).join("")
    : `<div class="msg bot">Hi! Ask me about your portfolio's spread, sector exposure, indicators or risk signals.</div>`; log.scrollTop = log.scrollHeight; };
  const send = async text => {
    text = (text || "").trim(); if (!text) return; inp.value = "";
    const hist = S.chat.filter(m => !m.err).slice(-8).map(m => ({ role: m.role, content: m.content }));
    S.chat.push({ role: "user", content: text }); S.chat.push({ role: "assistant", content: "Thinking…" }); draw();
    try {
      const r = await api("/chat", { holdings: holdings(), message: text, history: hist });
      S.chat.pop();
      S.chat.push(r.ok ? { role: "assistant", content: r.reply } : { role: "assistant", content: r.error, err: true });
    } catch (e) { S.chat.pop(); S.chat.push({ role: "assistant", content: "AI temporarily unavailable — please retry", err: true }); }
    draw();
  };
  $(`#${id}-send`).onclick = () => send(inp.value);
  inp.onkeydown = e => { if (e.key === "Enter") send(inp.value); };
  document.querySelectorAll(`#${id}-log ~ .chips .chip`).forEach(b => b.onclick = () => send(b.dataset.chip));
  draw();
}

/* ---------- news ---------- */
function newsHtml(n) {
  const errs = (n.errors || []).length ? `<p class="small warn">${esc(n.errors.join(" · "))}</p>` : "";
  if (!n.items.length) return `<p>No articles available right now.</p>${errs}`;
  return `${n.note ? `<p class="small warn">${esc(n.note)}</p>` : ""}${errs}` + n.items.map(i => `<div class="news">
    ${i.link ? `<a href="${esc(i.link)}" target="_blank" rel="noopener noreferrer">${esc(i.title)}</a>` : `<b>${esc(i.title)}</b>`}
    <div class="small"><span class="tag ${i.sentiment}">${i.sentiment}</span> ${i.ticker ? esc(i.ticker) + " · " : ""}${esc(i.source || "Unknown source")} · ${ago(i.published_at)}</div></div>`).join("");
}

/* ---------- views ---------- */
const V = {};
V.import = async m => {
  let draft = [], tab = "file";
  m.innerHTML = `<section class="reveal"><h1>Add your portfolio</h1>
  <p>Upload a broker statement (CSV or PDF), paste your holdings as text, or add stocks one by one. You review and edit everything before saving. Your data stays in this browser.</p>
  <div class="card"><div class="tabs"><button class="chip on" data-t="file">Upload CSV / PDF</button><button class="chip" data-t="text">Paste text</button><button class="chip" data-t="manual">Add manually</button></div>
  <div id="bidup101-tab"></div><div id="bidup101-imsg" style="margin-top:1rem"></div></div></section>
  <section class="reveal" id="bidup101-review"></section>
  <section class="reveal"><div class="card"><h3>Broker sync</h3><p>Live sync with Zerodha / Upstox is <b>Coming Soon</b>. File upload, pasted text and manual entry are supported for now.</p>
  <button class="btn ghost" id="bidup101-demo">Load demo portfolio</button> <span class="small">optional shortcut</span></div></section>`;
  const msg = $("#bidup101-imsg");
  const say = (h) => { msg.innerHTML = h; };
  const tabHtml = {
    file: `<input type="file" id="bidup101-file" accept=".csv,.pdf,.txt,text/csv,application/pdf,text/plain"><p class="small">CSV works best. PDFs must contain selectable text (not a scan) and not be password-locked. Max 8 MB.</p>`,
    text: `<textarea id="bidup101-paste" placeholder="Examples:&#10;TCS 10 3500&#10;Infosys, 25, 1500&#10;10 shares of ITC at 400"></textarea><p><button class="btn" id="bidup101-read">Read holdings</button></p>`,
    manual: `<p class="small">Use the "Add a stock" box below.</p>`};
  const showTab = () => {
    m.querySelectorAll(".tabs .chip").forEach(c => c.classList.toggle("on", c.dataset.t === tab));
    $("#bidup101-tab").innerHTML = tabHtml[tab];
    const f = $("#bidup101-file"); if (f) f.onchange = onFile;
    const r = $("#bidup101-read"); if (r) r.onclick = () => submit({ csv: $("#bidup101-paste").value });
  };
  m.querySelectorAll(".tabs .chip").forEach(c => c.onclick = () => { tab = c.dataset.t; showTab(); });

  async function submit(body) {
    say(`<div class="small">Reading your file and matching stocks… names outside the top-38 list are looked up online, so this can take up to a minute.</div>`);
    try {
      const r = await api("/portfolio/import", body);
      if (!r.ok) { say(`<div class="err">${esc(r.error)}</div><p class="small">You can still add stocks one by one below.</p>`); return; }
      draft = r.holdings.map(h => ({ ticker: h.ticker, name: h.name, sector: h.sector, extra: !!h.symbol, quantity: h.quantity, avg_buy_price: h.avg_buy_price }))
        .concat(r.unresolved.map(u => ({ ticker: "", srcName: u.name, quantity: u.quantity, avg_buy_price: u.avg_buy_price })));
      say(`<div class="ok">${esc(r.message)}</div>${(r.warnings || []).map(w => `<div class="warn" style="margin-top:.5rem">${esc(w)}</div>`).join("")}`);
      review();
    } catch (e) { say(errBox(e)); }
  }
  function onFile(e) {
    const f = e.target.files[0]; if (!f) return;
    if (f.size > 8 * 1024 * 1024) { say(`<div class="err">File is larger than 8 MB.</div>`); return; }
    const pdf = /\.pdf$/i.test(f.name) || f.type === "application/pdf", rd = new FileReader();
    rd.onload = () => submit(pdf ? { pdf_base64: String(rd.result).split(",")[1] } : { csv: String(rd.result) });
    pdf ? rd.readAsDataURL(f) : rd.readAsText(f);
  }

  function review() {
    const box = $("#bidup101-review");
    box.innerHTML = `<h2>Review your holdings</h2><div class="card">
    ${draft.length ? `<div class="wrap"><table><tr><th>Stock</th><th>Sector</th><th>Quantity</th><th>Avg buy price (₹)</th><th></th></tr>
    ${draft.map((d, i) => `<tr class="${d.ticker ? "" : "rowbad"}"><td>${d.ticker ? `<b>${esc(d.ticker.replace(/\.(NS|BO)$/, ""))}</b><div class="small">${esc(d.name || "")}</div>`
      : `<div class="small">Couldn't match: <b>${esc(d.srcName)}</b></div><div class="row"><input data-q="${i}" placeholder="Company name or ticker"><button class="btn ghost" data-fix="${i}">Find</button></div>`}</td>
    <td>${esc(d.sector || (d.ticker ? "" : "–"))}</td><td><input class="num" type="number" min="0" step="any" data-i="${i}" data-k="quantity" value="${d.quantity}"></td>
    <td><input class="num" type="number" min="0" step="any" data-i="${i}" data-k="avg_buy_price" value="${d.avg_buy_price}"></td><td><button class="link" data-rm="${i}">Remove</button></td></tr>`).join("")}</table></div>` : `<p class="small">No holdings yet. Upload a file above or add a stock below.</p>`}
    <h3 style="margin-top:1.2rem">Add a stock</h3>
    <div class="row"><input id="bidup101-aq" placeholder="Company name or ticker, e.g. Infosys or RBA"><input class="num" id="bidup101-aqty" type="number" min="0" step="any" placeholder="Qty"><input class="num" id="bidup101-apx" type="number" min="0" step="any" placeholder="Avg price ₹"><button class="btn ghost" id="bidup101-add">Add</button></div>
    <div id="bidup101-addmsg" class="small" style="margin-top:.5rem"></div>
    <hr style="border:0;border-top:1px solid var(--line);margin:1.2rem 0"><div class="row"><input id="bidup101-pname" placeholder="Portfolio name (optional)" style="max-width:260px"><button class="btn" id="bidup101-save">Save portfolio</button></div><div id="bidup101-savemsg" style="margin-top:.7rem"></div></div>`;
    box.querySelectorAll("input[data-i]").forEach(inp => inp.onchange = () => { draft[+inp.dataset.i][inp.dataset.k] = parseFloat(inp.value) || 0; });
    box.querySelectorAll("[data-rm]").forEach(b => b.onclick = () => { draft.splice(+b.dataset.rm, 1); review(); });
    box.querySelectorAll("[data-fix]").forEach(b => b.onclick = async () => {
      const i = +b.dataset.fix, q = box.querySelector(`[data-q="${i}"]`).value; if (!q.trim()) return;
      b.textContent = "…";
      try { const r = await api("/portfolio/resolve", { query: q }); if (r.ok) { Object.assign(draft[i], { ticker: r.ticker, name: r.name, sector: r.sector, extra: !r.curated }); review(); } else { b.textContent = "Find"; alert(r.error); } }
      catch (e) { b.textContent = "Find"; alert(e.message); }
    });
    $("#bidup101-add").onclick = async () => {
      const q = $("#bidup101-aq").value, qty = parseFloat($("#bidup101-aqty").value), px = parseFloat($("#bidup101-apx").value), am = $("#bidup101-addmsg");
      if (!q.trim() || !(qty > 0) || !(px >= 0)) { am.innerHTML = `<span class="neg">Enter a company or ticker, a quantity above 0, and your average buy price.</span>`; return; }
      am.textContent = "Looking it up…";
      try {
        const r = await api("/portfolio/resolve", { query: q });
        if (!r.ok) { am.innerHTML = `<span class="neg">${esc(r.error)}</span>`; return; }
        const ex = draft.find(d => d.ticker === r.ticker);
        if (ex) { ex.avg_buy_price = (ex.quantity * ex.avg_buy_price + qty * px) / (ex.quantity + qty); ex.quantity += qty; }
        else draft.push({ ticker: r.ticker, name: r.name, sector: r.sector, extra: !r.curated, quantity: qty, avg_buy_price: px });
        review();
      } catch (e) { am.innerHTML = `<span class="neg">${esc(e.message)}</span>`; }
    };
    $("#bidup101-save").onclick = () => {
      const ok = draft.filter(d => d.ticker && d.quantity > 0 && d.avg_buy_price >= 0), dropped = draft.length - ok.length, sm = $("#bidup101-savemsg");
      if (!ok.length) { sm.innerHTML = `<div class="err">Add at least one matched holding with a quantity above 0.</div>`; return; }
      const hs = ok.map(d => ({ ticker: d.ticker, quantity: d.quantity, avg_buy_price: d.avg_buy_price, ...(d.extra ? { name: d.name, sector: d.sector } : {}) }));
      let name = $("#bidup101-pname").value.trim() || "My portfolio", n = name, i = 2;
      while (S.portfolios[n] && n !== S.active) n = `${name} (${i++})`;
      S.portfolios[n] = hs; S.active = n; persist();
      sm.innerHTML = `<div class="ok">Saved ${hs.length} holding${hs.length === 1 ? "" : "s"}${dropped ? ` (${dropped} unmatched row${dropped === 1 ? "" : "s"} left out)` : ""}.</div><p><a class="btn" href="#/home">Open dashboard</a></p>`;
    };
  }
  $("#bidup101-demo").onclick = async () => { try { S.portfolios["Demo portfolio"] = await api("/demo"); S.active = "Demo portfolio"; persist(); location.hash = "#/home"; } catch (e) { say(errBox(e)); } };
  showTab(); review();
};

const FEATURES = [
  { r: "portfolio", ic: "📊", title: "Portfolio", desc: "Track value, P&L and sector exposure for every holding." },
  { r: "simulator", ic: "🧪", title: "Simulator", desc: "Add hypothetical stocks and see how they'd have performed." },
  { r: "screener", ic: "🔎", title: "Screener", desc: "Describe what you want in plain English, we filter the data." },
  { r: "stock", ic: "📈", title: "Stock Detail", desc: "Chart, indicators and news for any supported stock." },
  { r: "gat", ic: "🕸️", title: "Risk Analytics", desc: "Cross-sector risk signals from the GAT model." },
  { r: "compare", ic: "⚖️", title: "Compare", desc: "Put two or more saved portfolios side by side." },
];
function featureGrid() {
  return `<div class="feature-grid">${FEATURES.map(f => `<a class="feature-card" href="#/${f.r}"><span class="ic">${f.ic}</span><h3>${f.title}</h3><p>${f.desc}</p></a>`).join("")}</div>`;
}

V.home = async m => {
  m.innerHTML = `<section class="hero-main reveal">
    <h1>All your investments.<br><span class="tag-accent">One intelligent dashboard.</span></h1>
    <p>Track your portfolio, understand your risk, screen new ideas and ask questions in plain language — all in one place.</p>
    <div class="hero-stats"><div><b>38+</b>stocks covered</div><div><b>9</b>sectors tracked</div><div><b>Free</b>&amp; educational</div></div>
    ${featureGrid()}</section>
  <section class="reveal"><h2>Ask the assistant</h2>${chatBox("bidup101-hc")}</section>
  <section class="card hero reveal" id="bidup101-health">${spin("Analysing your portfolio…")}</section>
  <section class="reveal"><h2 id="bidup101-nl">News for your holdings</h2><div class="card" id="bidup101-news">${spin("Loading news…")}</div></section>`;
  bindChat("bidup101-hc");
  api("/news", { holdings: holdings() }).then(n => { $("#bidup101-nl").textContent = n.label === "Portfolio News" ? "News for your holdings" : "Market News"; $("#bidup101-news").innerHTML = newsHtml(n); })
    .catch(e => $("#bidup101-news").innerHTML = errBox(e));
  try {
    const o = await api("/overview", { holdings: holdings() }); const p = o.portfolio;
    ingestAlerts(o.risk);
    $("#bidup101-health").innerHTML = `<h2>Portfolio Health</h2>
    <div class="grid g2"><div><p class="small">Is my money spread out or concentrated?</p>
      <h1><span class="band ${p.band.level}">${esc(p.band.label)}</span></h1><p>${esc(p.band.text)}</p>
      <p class="small"><span class="tip" title="${esc(p.hhi_explain)}">Concentration score (HHI): ${p.hhi}</span> — ${esc(p.hhi_explain)}</p>
      <p><b>${inr(p.total_value)}</b> · <span class="${cls(p.pnl)}">${pct(p.pnl_pct)} overall</span> · ${p.num_holdings} holdings, ${p.num_sectors} sectors</p></div>
      <div><p class="small">Which sectors am I most exposed to?</p>${bars(p.sector_weights)}</div></div>
    <h3 style="margin-top:1.5rem">Is there a risk alert right now?</h3>${alertsHtml(o.risk)}${disclosure(o.risk)}
    <p class="small">${priceLabel(p.prices_as_of)}</p>`;
  } catch (e) { $("#bidup101-health").innerHTML = `<h2>Portfolio Health</h2>${errBox(e)}`; }
};

V.portfolio = async m => {
  m.innerHTML = `<section class="reveal"><h1>Portfolio · ${esc(S.active)}</h1><div id="bidup101-pt">${spin()}</div></section>
  <section class="reveal"><div class="card"><h3>Broker sync</h3><p>Live broker sync is <b>Coming Soon</b>. Use <a href="#/import">CSV import</a> for now.</p></div></section>`;
  try {
    const o = await api("/overview", { holdings: holdings() }); const p = o.portfolio;
    $("#bidup101-pt").innerHTML = `<div class="card"><div class="grid g3"><div><div class="small">Value</div><h2>${inr(p.total_value)}</h2></div>
    <div><div class="small">Invested</div><h2>${inr(p.total_cost)}</h2></div><div><div class="small">P&amp;L</div><h2 class="${cls(p.pnl)}">${inr(p.pnl)} (${pct(p.pnl_pct)})</h2></div></div>
    <p class="small">${priceLabel(p.prices_as_of)}${o.market.quote_error ? " · Refresh issue, showing last known prices." : ""}</p>
    <div class="wrap"><table><tr><th>Stock</th><th>Sector</th><th>Qty</th><th>Avg cost</th><th>Price</th><th>Day</th><th>P&amp;L</th><th>Weight</th></tr>
    ${p.holdings.map(h => `<tr><td><a href="#/stock/${h.ticker}"><b>${h.ticker}</b></a><div class="small">${esc(h.name)}</div></td><td>${h.sector}</td><td>${h.quantity}</td><td>${inr(h.avg_buy_price)}</td>
    <td>${inr(h.price)}${!h.price_found ? ' <span class="small" title="No live price found, cost price shown">(cost)</span>' : h.stale ? ' <span class="small" title="Last known price">*</span>' : ""}</td><td class="${cls(h.day_change_pct || 0)}">${pct(h.day_change_pct)}</td><td class="${cls(h.pnl)}">${pct(h.pnl_pct)}</td><td>${(h.weight * 100).toFixed(1)}%</td></tr>`).join("")}</table></div></div>
    <div class="card" style="margin-top:1rem"><h3>Sector exposure</h3>${bars(p.sector_weights)}</div>`;
  } catch (e) { $("#bidup101-pt").innerHTML = errBox(e); }
};

V.chat = async m => { m.innerHTML = `<section class="reveal"><h1>Chat</h1>${chatBox("bidup101-cc", true)}</section>`; bindChat("bidup101-cc"); };

V.screener = async m => {
  const ex = ["IT and banking stocks with RSI below 40", "Low risk pharma or FMCG", "Oversold stocks excluding metals", "High risk energy stocks"];
  m.innerHTML = `<section class="reveal"><h1>Stock Screener</h1><p>Describe what you're looking for in plain English.</p><div class="card">
  <div class="row"><input id="bidup101-sq" placeholder="e.g. low risk IT stocks with RSI below 45"><button class="btn" id="bidup101-sgo">Screen</button></div>
  <div class="chips">${ex.map(x => `<button class="chip">${esc(x)}</button>`).join("")}</div></div><div id="bidup101-sres" style="margin-top:1rem"></div></section>`;
  const run = async q => {
    if (!q.trim()) return; $("#bidup101-sres").innerHTML = spin("Screening…");
    try {
      const r = await api("/screener", { query: q });
      $("#bidup101-sres").innerHTML = `<div class="card"><p class="small">Understood as: <b>${esc(r.interpreted_as)}</b> (parsed by ${r.parser}) · ${r.count} match${r.count === 1 ? "" : "es"}</p>
      <div class="wrap"><table><tr><th>Stock</th><th>Sector</th><th>Price</th><th>RSI</th><th>1M</th><th>Volatility</th><th>Risk</th></tr>${r.results.map(x => `<tr><td><a href="#/stock/${x.ticker}"><b>${x.ticker}</b></a><div class="small">${esc(x.name)}</div></td><td>${x.sector}</td><td>${inr(x.price)}</td><td>${x.rsi ?? "–"}</td><td class="${cls(x.return_1m_pct)}">${pct(x.return_1m_pct)}</td><td>${x.volatility_pct}%</td><td>${x.risk}</td></tr>`).join("")}</table></div>
      <p class="small">${esc(r.note)}</p></div>`;
    } catch (e) { $("#bidup101-sres").innerHTML = errBox(e); }
  };
  $("#bidup101-sgo").onclick = () => run($("#bidup101-sq").value);
  $("#bidup101-sq").onkeydown = e => { if (e.key === "Enter") run(e.target.value); };
  m.querySelectorAll(".chip").forEach(c => c.onclick = () => { $("#bidup101-sq").value = c.textContent; run(c.textContent); });
};

V.stock = async (m, arg) => {
  if (!S.universe) { try { S.universe = await api("/universe"); } catch (e) { m.innerHTML = errBox(e); return; } }
  const t = (arg || "").toUpperCase();
  m.innerHTML = `<section class="reveal"><h1>Stock Detail</h1><div class="row"><select id="bidup101-ssel"><option value="">Choose a stock…</option>
  ${S.universe.map(u => `<option value="${u.ticker}" ${u.ticker === t ? "selected" : ""}>${u.ticker} — ${esc(u.name)}</option>`).join("")}</select></div></section><div id="bidup101-sd"></div>`;
  $("#bidup101-ssel").onchange = e => { if (e.target.value) location.hash = "#/stock/" + e.target.value; };
  if (!t) { $("#bidup101-sd").innerHTML = `<p>Pick a stock to see its chart, indicators, news and a portfolio what-if.</p>`; return; }
  $("#bidup101-sd").innerHTML = spin();
  const load = async amount => {
    try {
      const d = await api("/stock/" + t, { holdings: holdings(), amount });
      const i = d.indicators, q = d.quote;
      $("#bidup101-sd").innerHTML = `<section class="reveal card"><div class="row" style="justify-content:space-between"><div><h2>${d.ticker} · ${esc(d.name)}</h2><span class="small">${d.sector}</span></div>
      <div><h2>${inr(q ? q.price : i.price)} <span class="${cls(q ? q.change_pct : 0)}">${q ? pct(q.change_pct, 2) : ""}</span></h2><span class="small">${q ? priceLabel(q.as_of) : ""}${q && q.stale ? " · last known price" : ""}</span></div></div>
      <div style="height:320px"><canvas id="bidup101-ch"></canvas></div></section>
      <section class="reveal"><h2>Indicators in plain language</h2><div class="grid g3">${Object.entries(i.explanations).map(([k, v]) => `<div class="card"><h3 style="font-size:1rem">${esc(k)}</h3><p>${esc(v)}</p></div>`).join("")}</div>
      <p class="small">Indicators describe past price behaviour. They are not predictions or recommendations.</p></section>
      <section class="reveal"><h2>What if this stock were added to my portfolio?</h2><div class="card"><div class="row"><input id="bidup101-amt" type="number" min="0" placeholder="Amount in ₹, e.g. 50000" value="${amount || ""}"><button class="btn" id="bidup101-sim">Simulate</button></div>
      <p id="bidup101-simout">${d.impact ? esc(d.impact.text) : '<span class="small">Enter an amount to see how your sector exposure and concentration would change (illustration only).</span>'}</p></div></section>
      <section class="reveal"><h2>News</h2><div class="card">${newsHtml({ items: d.news.items, errors: d.news.error ? [d.news.error] : [] })}</div></section>`;
      $("#bidup101-sim").onclick = () => load(parseFloat($("#bidup101-amt").value) || 0);
      const c = i.chart; if (S.chart) S.chart.destroy();
      S.chart = new Chart($("#bidup101-ch"), { type: "line", data: { labels: c.dates, datasets: [
        { label: "Close", data: c.close, borderColor: "#6246ea", borderWidth: 2, pointRadius: 0, tension: .1 },
        { label: "20d avg", data: c.sma, borderColor: "#2b2c34", borderWidth: 1, pointRadius: 0, borderDash: [4, 4] },
        { label: "Upper band", data: c.upper, borderColor: "#d1d1e9", borderWidth: 1, pointRadius: 0 },
        { label: "Lower band", data: c.lower, borderColor: "#d1d1e9", borderWidth: 1, pointRadius: 0, fill: "-1", backgroundColor: "#d1d1e933" }] },
        options: { maintainAspectRatio: false, interaction: { mode: "index", intersect: false }, scales: { x: { ticks: { maxTicksLimit: 8 } } } } });
      reveal();
    } catch (e) { $("#bidup101-sd").innerHTML = errBox(e); }
  };
  load(0);
};

V.gat = async m => {
  m.innerHTML = `<section class="reveal"><h1>Cross-Sector Risk (GAT)</h1><div id="bidup101-g">${spin()}</div></section>`;
  try {
    const o = await api("/overview", { holdings: holdings() }), r = o.risk;
    if (r.error) { $("#bidup101-g").innerHTML = errBox(r.error); return; }
    ingestAlerts(r);
    $("#bidup101-g").innerHTML = `<div class="card"><h3>Your risk signals</h3>${alertsHtml(r)}${disclosure(r)}<p class="small">Method: <b>${esc(r.method)}</b> · data as of ${r.as_of} · alert threshold ${r.threshold}</p></div>
    <div class="card" style="margin-top:1rem"><h3>Stress by sector</h3><p class="small">Stress = recent decline or unusual volatility. Model score = chance-like signal of near-term adverse move after graph propagation.</p>
    <div class="wrap"><table><tr><th>Node</th><th>Stress</th><th>Model score</th><th>5d move (σ)</th><th>Vol ratio</th></tr>${r.nodes.slice().sort((a, b) => b.score - a.score).map(n => `<tr><td>${esc(n.node)}</td><td>${n.stress}</td><td><b>${n.score}</b></td><td>${n.z5}</td><td>${n.vol_ratio}</td></tr>`).join("")}</table></div></div>
    <div class="card" style="margin-top:1rem"><h3>Strongest links (attention)</h3><div class="wrap"><table><tr><th>Affected</th><th>Influenced by</th><th>Attention</th><th>Correlation</th></tr>${r.edges.slice(0, 12).map(e => `<tr><td>${esc(e.target)}</td><td>${esc(e.source)}</td><td>${e.attention}</td><td>${e.correlation}</td></tr>`).join("")}</table></div></div>
    ${r.trained ? `<div class="card" style="margin-top:1rem"><h3>Held-out test metrics</h3><pre class="md">${esc(JSON.stringify(r.metrics, null, 2))}</pre></div>` : ""}`;
  } catch (e) { $("#bidup101-g").innerHTML = errBox(e); }
};

V.compare = async m => {
  const names = Object.keys(S.portfolios);
  m.innerHTML = `<section class="reveal"><h1>Portfolio Comparison</h1><div class="card"><p>Select 2–4 saved portfolios (each CSV import is saved by name).</p>
  ${names.map(n => `<label style="display:block"><input type="checkbox" class="bidup101-cmp" value="${esc(n)}" ${n === S.active ? "checked" : ""}> ${esc(n)} <span class="small">(${S.portfolios[n].length} holdings)</span></label>`).join("")}
  <p><button class="btn" id="bidup101-cgo">Compare</button> <a href="#/import">Import another</a></p></div><div id="bidup101-cres" style="margin-top:1rem"></div></section>`;
  $("#bidup101-cgo").onclick = async () => {
    const sel = [...document.querySelectorAll(".bidup101-cmp:checked")].map(x => x.value);
    if (sel.length < 2 || sel.length > 4) { $("#bidup101-cres").innerHTML = `<div class="warn">Please select between 2 and 4 portfolios.</div>`; return; }
    $("#bidup101-cres").innerHTML = spin("Comparing…");
    try {
      const r = await api("/compare", { portfolios: sel.map(n => ({ name: n, holdings: S.portfolios[n] })) });
      const secs = [...new Set(r.flatMap(x => Object.keys(x.portfolio.sector_weights)))];
      const row = (l, f) => `<tr><th>${l}</th>${r.map(x => `<td>${f(x)}</td>`).join("")}</tr>`;
      $("#bidup101-cres").innerHTML = `<div class="card wrap"><table><tr><th></th>${r.map(x => `<th>${esc(x.name)}</th>`).join("")}</tr>
      ${row("Value", x => inr(x.portfolio.total_value))}${row("Holdings", x => x.portfolio.num_holdings)}
      ${row("Concentration", x => `<span class="band ${x.portfolio.band.level}">${esc(x.portfolio.band.label)}</span> <span class="small">HHI ${x.portfolio.hhi}</span>`)}
      ${secs.map(s => row(s, x => ((x.portfolio.sector_weights[s] || 0) * 100).toFixed(1) + "%")).join("")}
      ${row("Risk signals", x => (x.risk.alerts || []).map(a => `<div class="alert ${a.level}">${esc(a.text)}</div>`).join("") || "None")}</table></div>`;
    } catch (e) { $("#bidup101-cres").innerHTML = errBox(e); }
  };
};

V.simulator = async m => {
  if (!S.universe) { try { S.universe = await api("/universe"); } catch (e) { m.innerHTML = errBox(e); return; } }
  const opts = S.universe.map(u => `<option value="${u.ticker}">${u.ticker} — ${esc(u.name)}</option>`).join("");
  let rows = [{ ticker: "", quantity: "" }];
  const haveBase = holdings().length > 0;
  m.innerHTML = `<section class="reveal"><h1>Portfolio Simulator</h1>
  <p>${haveBase ? `Add stocks below to see how your <b>${esc(S.active)}</b> portfolio would have performed with them included.`
    : "No saved portfolio yet — add stocks below to simulate a standalone mini-portfolio on its own."}</p>
  <div class="card"><div id="bidup101-simrows"></div>
  <button class="btn ghost" id="bidup101-simadd">+ Add stock</button>
  <div class="row" style="margin-top:1rem"><label class="small">Period&nbsp;
    <select id="bidup101-simperiod"><option value="3m">3 months</option><option value="6m">6 months</option>
    <option value="1y" selected>1 year</option><option value="3y">3 years</option></select></label>
    <button class="btn" id="bidup101-simgo">Run simulation</button></div></div>
  <div id="bidup101-simres" style="margin-top:1rem"></div></section>`;
  const rowsEl = $("#bidup101-simrows");
  const drawRows = () => { rowsEl.innerHTML = rows.map((r, i) => `<div class="sim-row">
    <select data-i="${i}" class="sim-t"><option value="">Choose a stock…</option>${opts}</select>
    <input data-i="${i}" class="sim-q" type="number" min="1" placeholder="Quantity" value="${r.quantity}">
    <button class="remove-btn" data-i="${i}">✕</button></div>`).join("");
    rowsEl.querySelectorAll(".sim-t").forEach(s => { s.value = rows[s.dataset.i].ticker; s.onchange = () => rows[s.dataset.i].ticker = s.value; });
    rowsEl.querySelectorAll(".sim-q").forEach(inp => inp.oninput = () => rows[inp.dataset.i].quantity = inp.value);
    rowsEl.querySelectorAll(".remove-btn").forEach(b => b.onclick = () => { rows.splice(b.dataset.i, 1); if (!rows.length) rows.push({ ticker: "", quantity: "" }); drawRows(); });
  };
  drawRows();
  $("#bidup101-simadd").onclick = () => { rows.push({ ticker: "", quantity: "" }); drawRows(); };
  $("#bidup101-simgo").onclick = async () => {
    const additions = rows.filter(r => r.ticker && parseFloat(r.quantity) > 0).map(r => ({ ticker: r.ticker, quantity: parseFloat(r.quantity), avg_buy_price: 0 }));
    if (!additions.length) { $("#bidup101-simres").innerHTML = `<div class="warn">Add at least one stock with a quantity.</div>`; return; }
    $("#bidup101-simres").innerHTML = spin("Simulating…");
    try {
      const r = await api("/simulate", { base_holdings: holdings(), additions, period: $("#bidup101-simperiod").value });
      const c = Chart.getChart("bidup101-simch"); if (c) c.destroy();
      $("#bidup101-simres").innerHTML = `<div class="card">
        <div class="grid g3" style="margin-bottom:1rem">
          <div class="stat-box"><span class="small">With additions</span><b class="${cls(r.combined_total_return_pct)}">${pct(r.combined_total_return_pct)}</b></div>
          ${r.base_total_return_pct != null ? `<div class="stat-box"><span class="small">Without additions</span><b class="${cls(r.base_total_return_pct)}">${pct(r.base_total_return_pct)}</b></div>` : ""}
          <div class="stat-box"><span class="small">Max drawdown</span><b class="neg">${pct(r.max_drawdown_pct)}</b></div>
        </div>
        <div style="height:300px"><canvas id="bidup101-simch"></canvas></div>
        <h3 style="margin-top:1.5rem">Portfolio Health</h3>
        <div class="vs-health">
          ${r.base_health ? `<div><div class="small">Current (without additions)</div><span class="band ${r.base_health.band.level}">${esc(r.base_health.band.label)}</span><p class="small">HHI ${r.base_health.hhi} · ${inr(r.base_health.total_value)}</p></div>` : `<div><div class="small">Without additions</div><p class="small">No existing portfolio loaded.</p></div>`}
          <div><div class="small">With additions</div><span class="band ${r.combined_health.band.level}">${esc(r.combined_health.band.label)}</span><p class="small">HHI ${r.combined_health.hhi} · ${inr(r.combined_health.total_value)}</p></div>
        </div>
        <p class="small" style="margin-top:1rem">${esc(r.note)}</p></div>`;
      const datasets = [{ label: "With additions", data: r.combined_pct, borderColor: "#6246ea", borderWidth: 2, pointRadius: 0 }];
      if (r.base_pct) datasets.push({ label: "Without additions", data: r.base_pct, borderColor: "#d1d1e9", borderWidth: 2, pointRadius: 0, borderDash: [4, 4] });
      new Chart($("#bidup101-simch"), { type: "line", data: { labels: r.dates, datasets },
        options: { maintainAspectRatio: false, interaction: { mode: "index", intersect: false },
        scales: { x: { ticks: { maxTicksLimit: 8 } }, y: { ticks: { callback: v => v + "%" } } } } });
    } catch (e) { $("#bidup101-simres").innerHTML = errBox(e); }
  };
};

V.methodology = async m => {
  m.innerHTML = `<section class="reveal"><h1>Methodology &amp; Backtesting</h1><pre class="md" id="bidup101-md">Loading…</pre></section>`;
  try { $("#bidup101-md").textContent = (await api("/methodology")).markdown; } catch (e) { $("#bidup101-md").textContent = e.message; }
};

V.settings = async m => {
  m.innerHTML = `<section class="reveal"><h1>Settings</h1><div class="card"><label><input type="checkbox" id="bidup101-nt" ${S.notifyOn ? "checked" : ""}> Show alert notifications</label>
  <p class="small">Notifications are <b>simulated on a timer</b>: this page re-checks your risk signals every 60 seconds while open. There is no background push service.</p>
  <p><b>Saved portfolios:</b> ${Object.keys(S.portfolios).map(esc).join(", ") || "none"}</p>
  <button class="btn ghost" id="bidup101-clr">Delete all data stored in this browser</button></div></section>`;
  $("#bidup101-nt").onchange = e => { S.notifyOn = e.target.checked; save("bidup101_notify", S.notifyOn); };
  $("#bidup101-clr").onclick = () => { if (confirm("Delete all saved portfolios and alerts from this browser?")) { Object.keys(localStorage).filter(k => k.startsWith("bidup101_")).forEach(k => localStorage.removeItem(k)); S.portfolios = {}; S.active = null; S.alerts = []; location.hash = "#/import"; location.reload(); } };
};

/* ---------- notifications (simulated on a timer) ---------- */
function ingestAlerts(risk) {
  let added = 0;
  (risk.alerts || []).forEach(a => { if (!S.seen.has(a.key)) { S.seen.add(a.key); S.alerts.unshift({ ...a, at: new Date().toISOString() }); added++; if (S.notifyOn) toast(a.text); } });
  S.alerts = S.alerts.slice(0, 30); save("bidup101_alerts", S.alerts); save("bidup101_seen", [...S.seen]);
  const b = $("#bidup101-badge"); if (added) { b.textContent = Number(b.textContent || 0) + added; b.hidden = false; }
}
setInterval(async () => { if (!S.active || document.hidden) return; try { ingestAlerts((await api("/overview", { holdings: holdings() })).risk); } catch {} }, 60000);
$("#bidup101-bell").onclick = () => {
  const p = $("#bidup101-notif"); p.hidden = !p.hidden; $("#bidup101-badge").hidden = true; $("#bidup101-badge").textContent = "0";
  p.innerHTML = `<b>Alerts</b><p class="small">Simulated on a timer while this page is open — not live push.</p>` + (S.alerts.length ? S.alerts.map(a => `<div class="alert ${a.level}">${esc(a.text)}<div class="small">${ago(a.at)}</div></div>`).join("") : "<p>No alerts yet.</p>");
};
$("#bidup101-more").onclick = e => { e.stopPropagation(); $("#bidup101-menu").hidden = !$("#bidup101-menu").hidden; };
document.addEventListener("click", e => { if (!e.target.closest(".more")) $("#bidup101-menu").hidden = true; if (!e.target.closest("#bidup101-notif,#bidup101-bell")) $("#bidup101-notif").hidden = true; });

/* ---------- router ---------- */
const OPEN = ["import", "methodology", "settings", "simulator"];
async function route() {
  const [, name = "home", arg] = (location.hash || "#/home").split("/");
  $("#bidup101-menu").hidden = true;
  if (!V[name]) { location.hash = "#/home"; return; }
  if (!OPEN.includes(name) && !holdings().length) { location.hash = "#/import"; return; }
  document.querySelectorAll("#bidup101-nav a").forEach(a => a.classList.toggle("on", a.dataset.r === name));
  const m = $("#bidup101-main"); window.scrollTo(0, 0);
  try { await V[name](m, arg); } catch (e) { m.innerHTML = errBox(e); }
  reveal();
}
window.addEventListener("hashchange", route);
route();
})();
