// Page Statistiques (administrateurs) : utilisateurs actifs, entonnoir, usage des fonctionnalités et de l'IA.

const statsState = { days: 30, data: null, error: "", loading: false };

async function showStats() {
  view.className = "list";
  rerender = renderStats;
  Object.assign(statsState, { loading: true, error: "" });
  renderStats();
  try {
    statsState.data = await api(`/api/stats?days=${statsState.days}`);
  } catch (err) {
    statsState.error = err.message;
  }
  statsState.loading = false;
  if (location.hash.startsWith("#/stats")) renderStats();
}

const num = (n) => Number(n).toLocaleString(LOCALES[lang]);
const secs = (ms) => (ms == null ? "—" : `${(ms / 1000).toLocaleString(LOCALES[lang], { maximumFractionDigits: 1 })} s`);

function eventLabel(name) {
  const key = "event." + name;
  const label = t(key);
  return label === key ? name : label;
}

function tile(label, value, hint = "") {
  return `<div class="tile"><div class="micro">${label}</div><div class="tile-value">${value}</div>${hint ? `<div class="meta">${hint}</div>` : ""}</div>`;
}

// Barres verticales : une série (utilisateurs actifs), extrémités arrondies posées sur la ligne de base.
function dailyChart(daily) {
  const W = 720, H = 200, top = 12, bottom = 24, left = 32;
  const max = Math.max(1, ...daily.map((d) => d.users));
  const step = (W - left) / daily.length;
  const bar = Math.max(2, Math.min(24, step - 2));
  const y = (v) => top + (H - top - bottom) * (1 - v / max);
  const ticks = [...new Set([0, Math.ceil(max / 2), max])];
  const grid = ticks.map((v) => `<line class="grid" x1="${left}" x2="${W}" y1="${y(v)}" y2="${y(v)}"/><text class="axis" x="${left - 6}" y="${y(v) + 4}" text-anchor="end">${v}</text>`).join("");
  const bars = daily.map((d, i) => {
    const x = left + i * step + (step - bar) / 2;
    const h = H - bottom - y(d.users);
    const tip = esc(t("stats.dayTip", { date: fmtDate(d.day), users: d.users, events: d.events }));
    const r = Math.min(4, bar / 2, h);
    const path = h > 0
      ? `<path class="bar" d="M${x},${H - bottom} v${-(h - r)} q0,${-r} ${r},${-r} h${bar - 2 * r} q${r},0 ${r},${r} v${h - r} z"/>` : "";
    // Zone de survol plus grande que la barre.
    return `<g class="hit" tabindex="0" data-tip="${tip}"><rect x="${left + i * step}" y="${top}" width="${step}" height="${H - top - bottom}" fill="transparent"/>${path}</g>`;
  }).join("");
  const labels = [0, Math.floor(daily.length / 2), daily.length - 1].map((i) =>
    `<text class="axis" x="${i ? (i === daily.length - 1 ? W : left + i * step + step / 2) : left}" y="${H - 6}" text-anchor="${i ? (i === daily.length - 1 ? "end" : "middle") : "start"}">${fmtDate(daily[i].day)}</text>`).join("");
  return `<div class="chart-wrap"><svg viewBox="0 0 ${W} ${H}" role="img" aria-label="${t("stats.dailyTitle")}">${grid}${bars}${labels}</svg><div class="chart-tip" hidden></div></div>`;
}

function funnelChart(funnel) {
  const first = funnel[0]?.users || 0;
  return `<ol class="funnel">${funnel.map((f) => {
    const pct = first ? Math.round((f.users / first) * 100) : 0;
    return `<li><div class="funnel-label"><span>${t(f.label)}</span><span class="meta">${num(f.users)} · ${pct} %</span></div>
      <div class="funnel-track"><div class="funnel-bar" style="width:${first ? Math.max(f.users ? 1 : 0, pct) : 0}%"></div></div></li>`;
  }).join("")}</ol>`;
}

function table(head, rows) {
  if (!rows.length) return `<p class="meta">${t("stats.none")}</p>`;
  return `<div class="md-table"><table><thead><tr>${head.map((h, i) => `<th${i ? ' class="num"' : ""}>${h}</th>`).join("")}</tr></thead>
    <tbody>${rows.map((r) => `<tr>${r.map((c, i) => `<td${i ? ' class="num"' : ""}>${c}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
}

function renderStats() {
  const s = statsState;
  const d = s.data;
  const ranges = [7, 30, 90].map((n) => `<button type="button" class="btn${n === s.days ? " btn-primary" : ""}" data-days="${n}">${t("stats.days", { n })}</button>`).join("");
  let body = "";
  if (s.loading && !d) body = `<div class="banner loading" role="status"><span>${t("stats.loading")}</span><div class="progress"></div></div>`;
  else if (s.error) body = `<p class="banner error" role="status">${esc(s.error)}</p>`;
  else if (d) {
    const tt = d.totals;
    body = `
      <div class="tiles">
        ${tile(t("stats.users"), num(tt.users), t("stats.inRange", { n: d.days }))}
        ${tile(t("stats.activeToday"), num(tt.activeToday))}
        ${tile(t("stats.active7d"), num(tt.active7d))}
        ${tile(t("stats.sessions"), num(tt.sessions))}
        ${tile(t("stats.events"), num(tt.events))}
      </div>
      ${card(t("stats.dailyTitle"), dailyChart(d.daily)
        + `<details><summary class="link">${t("stats.showTable")}</summary>${table([t("stats.day"), t("stats.users"), t("stats.events")],
          d.daily.filter((x) => x.events).map((x) => [fmtDate(x.day), num(x.users), num(x.events)]))}</details>`)}
      <div class="cards">
        ${card(t("stats.funnelTitle"), `<p class="help">${t("stats.funnelHelp")}</p>${funnelChart(d.funnel)}`)}
        ${card(t("stats.aiTitle"), table([t("stats.feature"), t("stats.calls"), t("stats.errors"), t("stats.avg")],
          d.ai.map((a) => [eventLabel(a.event), num(a.calls), a.errors ? `<span class="err">${num(a.errors)}</span>` : "0", secs(a.avgMs)])))}
      </div>
      <div class="cards">
        ${card(t("stats.featuresTitle"), table([t("stats.event"), t("stats.count"), t("stats.users")],
          d.features.map((f) => [eventLabel(f.event), num(f.count), num(f.users)])))}
        ${card(t("stats.pagesTitle"), table([t("stats.page"), t("stats.views")], d.pages.map((p) => [esc(p.page), num(p.views)])))}
      </div>
      ${card(t("stats.errorsTitle"), table([t("stats.when"), t("stats.event"), t("stats.detail")],
        d.errors.map((e) => [esc(new Date(e.at).toLocaleString(LOCALES[lang])), eventLabel(e.event), esc(e.error)])))}
      <p class="meta">${t("stats.privacy")}</p>`;
  }
  view.innerHTML = `<header class="page-head"><h1>${t("nav.stats")}</h1><div class="tools">${ranges}</div></header>${body}`;

  view.onclick = (e) => {
    const pick = e.target.closest("[data-days]");
    if (!pick) return;
    statsState.days = Number(pick.dataset.days);
    showStats();
  };
  const tip = view.querySelector(".chart-tip");
  if (!tip) return;
  const show = (g) => {
    const box = view.querySelector(".chart-wrap").getBoundingClientRect();
    const r = g.getBoundingClientRect();
    tip.textContent = g.dataset.tip;
    tip.hidden = false;
    tip.style.left = `${Math.min(r.left - box.left + r.width / 2, box.width - 90)}px`;
  };
  view.querySelectorAll(".hit").forEach((g) => {
    g.onmouseenter = g.onfocus = () => show(g);
    g.onmouseleave = g.onblur = () => (tip.hidden = true);
  });
}
