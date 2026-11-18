const view = document.getElementById("view");
const STATUSES = ["notsent", "sent", "positive", "refused"];
const LOGO_COLORS = ["#1F2937", "#1E3A5F", "#334155", "#3F3F46", "#44403C", "#164E63"];
const SECTION_KINDS = ["offerLink", "keyPoints", "company", "cv", "letter", "email", "contact", "custom"];
const DEFAULT_SECTIONS = { regular: ["offerLink", "keyPoints", "cv", "email"], spontaneous: ["email", "cv"] };
const KEY_FIELDS = ["contract", "salary", "workMode", "experience", "start"];
const KEY_LISTS = ["responsibilities", "requirements"];

const ICONS = {
  inbox: '<path d="M3 12h5l1.5 3h5L16 12h5"/><path d="M3 12l3-7h12l3 7v7H3z"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="M16 16l5 5"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  filter: '<path d="M3 5h18l-7 8v6l-4 2v-8z"/>',
  chevron: '<path d="M6 9l6 6 6-6"/>',
  up: '<path d="M6 15l6-6 6 6"/>',
  back: '<path d="M15 5l-7 7 7 7"/>',
  edit: '<path d="M4 20h4L19 9l-4-4L4 16z"/>',
  close: '<path d="M6 6l12 12M18 6L6 18"/>',
  upload: '<path d="M12 16V4M6 10l6-6 6 6"/><path d="M4 20h16"/>',
  file: '<path d="M6 3h9l4 4v14H6z"/><path d="M15 3v4h4"/>',
  fileCheck: '<path d="M6 3h9l4 4v14H6z"/><path d="M15 3v4h4"/><path d="M9 13l2 2 4-4"/>',
  mail: '<path d="M3 5h18v14H3z"/><path d="M3 6l9 7 9-7"/>',
};
const GRIP = '<svg aria-hidden="true" width="16" height="16" viewBox="0 0 24 24" fill="#9CA3AF">'
  + [6, 12, 18].map((y) => `<circle cx="9" cy="${y}" r="1.6"/><circle cx="15" cy="${y}" r="1.6"/>`).join("") + "</svg>";

let userId; // undefined tant que Firebase n'a pas répondu, null si déconnecté
let apps = [];
let appsLoaded = false;
let rerender = () => {};

// ---------- Utilitaires ----------

function icon(name, size = 16, attrs = 'stroke="currentColor" stroke-width="1.75"') {
  return `<svg aria-hidden="true" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" ${attrs} stroke-linecap="square">${ICONS[name]}</svg>`;
}

function esc(text) {
  return String(text ?? "").replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
}

async function api(path, options = {}) {
  const isJson = options.body && !(options.body instanceof Blob);
  const resp = await fetch(path, {
    ...options,
    headers: isJson ? { "Content-Type": "application/json" } : {},
    body: isJson ? JSON.stringify(options.body) : options.body,
  });
  if (resp.status === 204) return null;
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) throw Object.assign(new Error(data.detail || `Error ${resp.status}`), { status: resp.status });
  return data;
}

function fmtDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  const opts = { month: "short", day: "numeric" };
  if (d.getFullYear() !== new Date().getFullYear()) opts.year = "numeric";
  return d.toLocaleDateString(LOCALES[lang], opts);
}

function logoColor(name) {
  let hash = 0;
  for (const c of name) hash = (hash * 31 + c.charCodeAt(0)) >>> 0;
  return LOGO_COLORS[hash % LOGO_COLORS.length];
}

function logo(name, big = false) {
  return `<div class="logo${big ? " big" : ""}" aria-hidden="true" style="background:${logoColor(name)}">${esc(name.charAt(0).toUpperCase())}</div>`;
}

function statusTag(status, big = false) {
  return `<span class="status status-${status}${big ? " big" : ""}">${t("status." + status)}</span>`;
}

function backLink(href, label) {
  return `<a class="back" href="${href}">${icon("back", 14, 'stroke="currentColor" stroke-width="2"')}${label}</a>`;
}

function fileUrl(file, download = false) {
  return `/api/files/${file.id}${download ? "?download=1" : ""}`;
}

function pagesLabel(n) {
  return t(n === 1 ? "file.page" : "file.pages", { n });
}

function section(app, kind) {
  return app.sections.find((s) => s.kind === kind);
}

async function loadApps() {
  apps = await api("/api/applications");
  appsLoaded = true;
  apps.sort((a, b) => (a.lastStatusChangeAt < b.lastStatusChangeAt ? 1 : -1));
  renderNav();
}

// ---------- Barre latérale et routes ----------

function renderNav() {
  const offers = location.hash.startsWith("#/offers");
  const current = (on) => (on ? ' aria-current="page"' : "");
  document.getElementById("nav").innerHTML = userId ? `
    <a href="#/"${current(!offers)}>${icon("inbox", 18)}<span class="grow">${t("nav.box")}</span><span class="count">${apps.length}</span></a>
    <a href="#/offers"${current(offers)}>${icon("search", 18)}<span>${t("nav.offers")}</span></a>
    <a href="#/signout">${icon("back", 18)}<span>${t("nav.signOut")}</span></a>` : "";
  document.getElementById("lang").innerHTML = Object.keys(LOCALES)
    .map((code) => `<button type="button" data-lang="${code}" aria-pressed="${code === lang}">${code.toUpperCase()}</button>`)
    .join("");
}

document.getElementById("lang").onclick = (e) => {
  const code = e.target.dataset.lang;
  if (!code) return;
  setLang(code);
  renderNav();
  rerender();
};

function route() {
  const [, page, id, sub] = location.hash.split("/");
  view.className = "";
  view.onclick = view.oninput = view.onchange = view.onsubmit = null;
  if (page !== "new" && sub !== "edit") form = null;
  renderNav();
  if (!userId) return showLogin();
  if (page === "signout") {
    location.hash = "#/";
    return authApi.signOut();
  }
  if (page === "offers") return showOfferSearch();
  if (page === "new") return showNew();
  if (page === "a" && sub === "edit") return showEdit(id);
  if (page === "a") return showDetail(id);
  return showBox();
}

window.onhashchange = route;

// ---------- Box ----------

const box = { filter: "all", menuOpen: false, query: "" };

async function showBox() {
  view.className = "list";
  rerender = renderBox;
  renderBox();
  try {
    await loadApps();
    renderBox();
  } catch (err) {
    view.innerHTML = `<div class="banner error" role="status">${esc(err.message)}</div>`;
  }
}

function renderBox() {
  const query = box.query.trim().toLowerCase();
  const shown = apps.filter((a) => (box.filter === "all" || a.status === box.filter)
    && `${a.company} ${a.jobTitle ?? ""}`.toLowerCase().includes(query));
  const filters = ["all", ...STATUSES].map((key) => {
    const count = key === "all" ? apps.length : apps.filter((a) => a.status === key).length;
    const label = key === "all" ? t("filter.all") : t("status." + key);
    return `<button type="button" data-filter="${key}" aria-pressed="${box.filter === key}">
      <span class="mark" aria-hidden="true"></span><span class="grow">${label}</span><span class="count">${count}</span></button>`;
  }).join("");
  const rows = shown.map((a) => `
    <div class="row">
      <div class="col-main">${logo(a.company)}
        <a class="row-link" href="#/a/${a.id}"><strong>${esc(a.company)}</strong><span>${esc(a.jobTitle || (a.type === "spontaneous" ? t("type.spontaneous") : ""))}</span></a>
      </div>
      <div class="col-status">${statusTag(a.status)}</div>
      <div class="col-date">${fmtDate(a.lastStatusChangeAt)}</div>
    </div>`).join("");

  view.innerHTML = `
    <header class="page-head">
      <h1>${t("nav.box")}</h1>
      <div class="tools">
        <input class="field search" type="search" id="box-search" value="${esc(box.query)}" placeholder="${t("box.search")}" aria-label="${t("box.search")}">
        <div class="menu-wrap">
          <button class="btn" type="button" id="filter-btn" aria-haspopup="true" aria-expanded="${box.menuOpen}">
            ${icon("filter")}<span>${box.filter === "all" ? t("filter.label") : t("filter.active", { status: t("status." + box.filter) })}</span>${icon("chevron", 14, 'stroke="currentColor" stroke-width="2"')}
          </button>
          ${box.menuOpen ? `<div class="menu" role="group" aria-label="${t("filter.group")}">${filters}</div>` : ""}
        </div>
        <a class="btn btn-primary" href="#/new">${icon("plus", 16, 'stroke="currentColor" stroke-width="2.25"')}<span>${t("box.new")}</span></a>
      </div>
    </header>
    <section class="table" aria-label="${t("box.applications")}">
      <div class="table-inner">
        <div class="row head"><div class="col-main">${t("box.colMain")}</div><div class="col-status">${t("box.colStatus")}</div><div class="col-date">${t("box.colDate")}</div></div>
        ${rows || (appsLoaded ? `<div class="row"><p class="meta">${t("box.empty")}</p></div>` : "")}
      </div>
    </section>`;

  view.onclick = (e) => {
    if (e.target.closest("#filter-btn")) {
      box.menuOpen = !box.menuOpen;
      renderBox();
    }
    const pick = e.target.closest("[data-filter]");
    if (pick) {
      Object.assign(box, { filter: pick.dataset.filter, menuOpen: false });
      renderBox();
    }
  };
  view.oninput = (e) => {
    if (e.target.id !== "box-search") return;
    box.query = e.target.value;
    renderBox();
    const input = document.getElementById("box-search");
    input.focus();
    input.setSelectionRange(input.value.length, input.value.length);
  };
}

// ---------- Page d'une candidature ----------

async function showDetail(id) {
  rerender = () => {};
  view.innerHTML = "";
  let app;
  try {
    app = await api(`/api/applications/${id}`);
  } catch (err) {
    view.innerHTML = backLink("#/", t("back.box")) + `<div class="banner error" role="status">${esc(err.message)}</div>`;
    return;
  }
  const expanded = { letter: false };
  rerender = () => renderDetail(app, expanded);
  rerender();
  view.onclick = (e) => {
    if (e.target.closest("[data-expand-letter]")) {
      expanded.letter = true;
      rerender();
    }
  };
}

function paras(text) {
  return text.split(/\n\s*\n/).map((p) => `<p>${esc(p.trim())}</p>`).join("");
}

function card(title, body, { cls = "", aside = "" } = {}) {
  return `<section class="card ${cls}"><div class="card-head"><h2>${title}</h2>${aside}</div><div class="card-body">${body}</div></section>`;
}

function kv(key, value) {
  return `<div class="kv"><div class="k">${key}</div><div class="v">${value}</div></div>`;
}

function keyPointsCard(s) {
  const values = KEY_FIELDS.filter((k) => s[k]).map((k) => kv(t("key." + k), esc(s[k]))).join("");
  const lists = KEY_LISTS.filter((k) => s[k]?.length)
    .map((k) => `<div><div class="micro">${t("key." + k)}</div><ul>${s[k].map((i) => `<li>${esc(i)}</li>`).join("")}</ul></div>`)
    .join("") + whyBlock(s.why, "key.whyOffer");
  if (!values && !lists) return "";
  return card(t("section.keyPoints"),
    (values ? `<div class="key-values">${values}</div>` : "") + (lists ? `<div class="key-lists">${lists}</div>` : ""),
    { cls: "key" });
}

function whyBlock(text, labelKey) {
  return text ? `<div><div class="micro">${t(labelKey)}</div><div class="prose">${paras(text)}</div></div>` : "";
}

function companyCard(s) {
  if (!s || !(s.summary || s.why)) return "";
  return card(t("section.company"),
    (s.summary ? `<div class="prose">${paras(s.summary)}</div>` : "") + whyBlock(s.why, "key.whyCompany"));
}

function offerCard(s) {
  if (!s?.rawText && !s?.url) return "";
  const open = s.url ? `<a class="link" href="${esc(s.url)}" target="_blank" rel="noopener">${t("detail.openOriginal")}</a>` : "";
  const body = s.rawText ? `<div class="prose scroll">${paras(s.rawText)}</div>` : `<a class="link" href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.url)}</a>`;
  return card(t("detail.jobOffer"), body, { cls: "wide", aside: open });
}

function cvCard(s, app, cls) {
  if (!s?.file) return "";
  const f = s.file;
  const when = app.sentAt ? t("file.versionSent", { date: fmtDate(app.sentAt) }) : t("file.added", { date: fmtDate(f.addedAt) });
  return card(t("detail.cvSent"), `
    <div class="file-tile">
      <img src="${fileUrl(f)}/preview" alt="">
      <div class="stack">
        <div><div class="file-name">${esc(f.name)}</div><div class="file-meta">${pagesLabel(f.pages)} · ${when}</div></div>
        <div class="actions">
          <a class="btn" href="${fileUrl(f)}" target="_blank" rel="noopener">${t("file.open")}</a>
          <a class="btn" href="${fileUrl(f, true)}">${t("file.download")}</a>
        </div>
      </div>
    </div>`, { cls });
}

function contactCard(s) {
  if (!s) return "";
  const parts = [];
  if (s.name || s.position) {
    parts.push(`<div class="kv">${s.name ? `<div class="person">${esc(s.name)}</div>` : ""}${s.position ? `<div class="meta">${esc(s.position)}</div>` : ""}</div>`);
  }
  if (s.phone) parts.push(kv(t("contact.phone"), `<a class="link" href="tel:${esc(s.phone.replace(/\s/g, ""))}">${esc(s.phone)}</a>`));
  if (s.email) parts.push(kv(t("contact.email"), `<a class="link" href="mailto:${esc(s.email)}">${esc(s.email)}</a>`));
  for (const x of s.extra || []) if (x.value) parts.push(kv(esc(x.label), esc(x.value)));
  return parts.length ? card(t("detail.contact"), parts.join(""), { cls: "contact" }) : "";
}

function emailCard(s, main = false) {
  if (!s || !(s.to || s.subject || s.sentAt || s.body)) return "";
  const meta = [["to", s.to], ["subject", s.subject], ["sent", s.sentAt]]
    .filter(([, v]) => v).map(([k, v]) => `<div>${t("email." + k)}: <span>${esc(v)}</span></div>`).join("");
  const body = s.body ? `${meta ? '<div class="rule"></div>' : ""}<div class="prose${main ? " big" : ""}">${paras(s.body)}</div>` : "";
  return card(t("section.email"), `<div class="mail-meta${main ? " inline" : ""}">${meta}</div>${body}`, { cls: main ? "key" : "" });
}

function letterCard(s, expanded) {
  if (!s || !(s.file || s.text)) return "";
  const paragraphs = (s.text || "").split(/\n\s*\n/);
  const cut = !expanded && paragraphs.length > 2;
  let body = s.text ? `<div class="prose">${paras(cut ? paragraphs.slice(0, 2).join("\n\n") : s.text)}${cut ? '<p class="more">…</p>' : ""}</div>` : "";
  if (s.file) body += `<div class="actions"><a class="btn" href="${fileUrl(s.file)}" target="_blank" rel="noopener">${t("detail.openLetter")}</a></div>`;
  else if (cut) body += `<div class="actions"><button class="btn" type="button" data-expand-letter>${t("detail.openLetter")}</button></div>`;
  return card(t("section.letter"), body, { aside: s.file ? `<span class="meta">${esc(s.file.name)}</span>` : "" });
}

function customCards(app) {
  return app.sections.filter((s) => s.kind === "custom" && (s.title || s.content))
    .map((s) => card(esc(s.title || t("section.custom")), `<div class="prose">${paras(s.content)}</div>`)).join("");
}

function row(...cards) {
  const html = cards.join("");
  return html ? `<div class="cards">${html}</div>` : "";
}

function renderDetail(app, expanded) {
  const regular = app.type === "regular";
  const dates = [t("detail.updated", { date: fmtDate(app.lastStatusChangeAt) })];
  if (app.sentAt) dates.push(t("detail.sent", { date: fmtDate(app.sentAt) }));
  const reference = [contactCard(section(app, "contact"))];
  const blocks = regular
    ? [keyPointsCard(section(app, "keyPoints") || {}),
       row(companyCard(section(app, "company"))),
       row(offerCard(section(app, "offerLink")), cvCard(section(app, "cv"), app, "narrowish")),
       row(...reference, emailCard(section(app, "email")), letterCard(section(app, "letter"), expanded.letter), customCards(app))]
    : [emailCard(section(app, "email"), true),
       row(companyCard(section(app, "company"))),
       row(...reference, cvCard(section(app, "cv"), app), letterCard(section(app, "letter"), expanded.letter), customCards(app))];

  view.innerHTML = `
    ${backLink("#/", t("back.box"))}
    <header class="detail-head">
      <div class="identity">${logo(app.company, true)}
        <div class="stack" style="gap:2px;min-width:0">
          <h1>${esc(regular ? app.jobTitle || app.company : app.company)}</h1>
          <div class="sub">${esc(regular ? app.company : app.jobTitle || t("type.spontaneous"))}</div>
        </div>
      </div>
      <div class="meta-bar">
        <span class="type-tag">${t(regular ? "type.regular" : "type.spontaneousShort")}</span>
        ${statusTag(app.status, true)}
        <span class="meta">${dates.join(" · ")}</span>
        <a class="btn" href="#/a/${app.id}/edit">${icon("edit")}${t("detail.edit")}</a>
      </div>
    </header>
    ${blocks.filter(Boolean).join("")}`;
}

// ---------- Formulaire (création et modification) ----------

let form = null;
let nextSectionId = 1;
let prefill = null;

function newSection(kind, values = {}) {
  const base = {
    offerLink: { url: "", paste: "" },
    keyPoints: { ...Object.fromEntries([...KEY_FIELDS, ...KEY_LISTS].map((k) => [k, ""])), why: "", filledByAi: false },
    company: { summary: "", why: "", filledByAi: false },
    cv: {},
    letter: { text: "" },
    email: { to: "", sentAt: "", subject: "", body: "" },
    contact: { name: "", position: "", email: "", phone: "", extra: [] },
    custom: { title: "", content: "" },
  }[kind];
  const s = { ...base, ...values, kind, id: values.id || `s${nextSectionId++}` };
  if (kind === "keyPoints") for (const k of KEY_LISTS) if (Array.isArray(s[k])) s[k] = s[k].join("\n");
  if (kind === "contact") s.extra = (s.extra || []).map((x) => ({ ...x }));
  return s;
}

function startForm(type, values = {}) {
  form = {
    type, company: "", jobTitle: "", status: "notsent", ai: "idle", menuOpen: false, saving: false, error: "",
    ...values,
    sections: (values.sections || DEFAULT_SECTIONS[type].map((kind) => ({ kind }))).map((s) => newSection(s.kind, s)),
  };
}

function showNew() {
  view.className = "";
  if (!form && prefill) {
    const { url, rawText, ...basics } = prefill;
    startForm("regular", basics);
    Object.assign(section(form, "offerLink"), { url, paste: rawText });
    prefill = null;
  }
  rerender = () => (form ? renderForm() : renderTypeStep());
  rerender();
}

function renderTypeStep() {
  view.innerHTML = `<div class="narrow">
    ${backLink("#/", t("back.box"))}
    <h1>${t("form.newTitle")}</h1>
    <div class="type-cards">
      <button class="btn type-card" type="button" data-type="regular">${icon("fileCheck", 28, 'stroke="#166534" stroke-width="1.5"')}${t("type.regular")}</button>
      <button class="btn type-card" type="button" data-type="spontaneous">${icon("mail", 28, 'stroke="#166534" stroke-width="1.5"')}${t("type.spontaneous")}</button>
    </div></div>`;
  view.onclick = (e) => {
    const pick = e.target.closest("[data-type]");
    if (!pick) return;
    startForm(pick.dataset.type);
    renderForm();
  };
}

async function showEdit(id) {
  rerender = () => {};
  view.innerHTML = "";
  if (!form || form.id !== id) {
    try {
      startForm(null, await api(`/api/applications/${id}`));
    } catch (err) {
      view.innerHTML = backLink("#/", t("back.box")) + `<div class="banner error" role="status">${esc(err.message)}</div>`;
      return;
    }
  }
  rerender = renderForm;
  renderForm();
}

function input(key, label, { type = "text", value = "", sec = "", ph = "", attrs = "", area = 0 } = {}) {
  const data = `data-key="${key}"${sec ? ` data-sec="${sec}"` : ""} ${attrs}`;
  const control = area
    ? `<textarea class="field" rows="${area}" placeholder="${esc(ph)}" ${data}>${esc(value)}</textarea>`
    : `<input class="field" type="${type}" placeholder="${esc(ph)}" value="${esc(value)}" ${data}>`;
  return `<label class="lbl"><span>${label}</span>${control}</label>`;
}

function chooser(s, labelKey) {
  return `<input type="file" accept="application/pdf" hidden data-file="${s.id}">
    <button class="btn" type="button" data-action="choose">${t(labelKey)}</button>`;
}

function dropZone(s, textKey) {
  const file = s._pending ? { name: s._pending.name } : s.file;
  if (file) {
    const meta = s._pending ? t("form.fileReady") : `${pagesLabel(file.pages)} · ${t("file.added", { date: fmtDate(file.addedAt) })}`;
    return `<div class="file-row">${icon("file", 22, 'stroke="#4B5563" stroke-width="1.5"')}
      <div><span class="file-name">${esc(file.name)}</span><span class="file-meta">${meta}</span></div>
      ${chooser(s, "form.replaceFile")}</div>`;
  }
  return `<div class="drop" data-drop="${s.id}">${icon("upload", 22, 'stroke="#4B5563" stroke-width="1.5"')}
    <span>${t(textKey)}</span>
    ${chooser(s, "form.chooseFile")}</div>`;
}

function aiBanner(where) {
  const f = form;
  if (f.ai === "loading") {
    return where === "link"
      ? `<div class="banner loading" role="status"><span>${t("ai.reading")}</span><div class="progress"></div></div>`
      : `<p class="banner loading" role="status">${t("ai.filling")}</p>`;
  }
  if (f.ai === "error" && where === "link") return `<p class="banner error" role="status">${esc(f.aiError)}</p>`;
  if (f.ai === "done") {
    return where === "link"
      ? `<p class="banner success" role="status">${t("ai.retrieved", { source: esc(f.aiSource) })}</p>`
      : `<p class="banner success">${t("ai.filled")}</p>`;
  }
  if (where === "link") return `<p class="help">${t(f.id ? "ai.helpEdit" : "ai.help")}</p>`;
  return `<p class="banner neutral">${t(section(f, "keyPoints").filledByAi ? "ai.filled" : "ai.idle")}</p>`;
}

function sectionBody(s) {
  const id = s.id;
  const busy = form.ai === "loading" ? "disabled" : "";
  switch (s.kind) {
    case "offerLink":
      return `<div class="fields">${input("url", t("form.offerUrl"), { type: "url", value: s.url, sec: id, ph: "https://" })}
          <button class="btn ${s.fetchedAt || form.ai === "done" ? "" : "btn-primary"}" type="button" data-action="fetch" ${busy}>${t(s.fetchedAt || form.ai === "done" ? "form.fetchAgain" : "form.fetch")}</button></div>
        <label class="check"><input type="checkbox" data-action="with-company" ${form.withCompany ? "checked" : ""} ${busy}>${t("form.withCompany")}</label>
        ${aiBanner("link")}
        ${input("paste", t("form.paste"), { value: s.paste, sec: id, ph: t("form.pastePh"), area: 3 })}`;
    case "keyPoints":
      return `${aiBanner("key")}
        <div class="fields">${KEY_FIELDS.map((k) => input(k, t("key." + k), { value: s[k], sec: id, ph: t("ph." + k), attrs: busy })).join("")}</div>
        <div class="fields">${KEY_LISTS.map((k) => input(k, t("form." + k), { value: s[k], sec: id, ph: t("ph." + k), attrs: busy, area: 4 })).join("")}</div>
        ${input("why", t("form.whyOffer"), { value: s.why, sec: id, ph: t("ph.why"), area: 3 })}`;
    case "company":
      return input("summary", t("form.companySummary"), { value: s.summary, sec: id, ph: t("ph.companySummary"), attrs: busy, area: 3 })
        + input("why", t("form.whyCompany"), { value: s.why, sec: id, ph: t("ph.why"), area: 3 });
    case "cv":
      return dropZone(s, "form.dropCv");
    case "letter":
      return dropZone(s, "form.dropLetter") + input("text", t("form.letterText"), { value: s.text, sec: id, ph: t("form.letterPh"), area: 4 });
    case "email":
      return `<div class="fields">${input("to", t("form.sentTo"), { type: "email", value: s.to, sec: id, ph: "name@company.com" })}
          ${input("sentAt", t("form.dateSent"), { value: s.sentAt, sec: id, ph: t("ph.dateSent") })}</div>
        ${input("subject", t("form.subject"), { value: s.subject, sec: id, ph: t("ph.subject") })}
        ${input("body", t("form.message"), { value: s.body, sec: id, ph: t("ph.message"), area: 6 })}`;
    case "contact":
      return `<div class="fields">
          ${input("name", t("form.name"), { value: s.name, sec: id, ph: t("ph.name") })}
          ${input("position", t("form.position"), { value: s.position, sec: id, ph: t("ph.position") })}
          ${input("email", t("contact.email"), { type: "email", value: s.email, sec: id, ph: "name@company.com" })}
          ${input("phone", t("contact.phone"), { type: "tel", value: s.phone, sec: id, ph: "+00 0 00 00 00 00" })}</div>
        ${s.extra.map((x, i) => `<div class="fields">
          ${input("label", t("form.fieldName"), { value: x.label, sec: id, ph: t("ph.fieldName"), attrs: `data-extra="${i}"` })}
          ${input("value", t("form.fieldValue"), { value: x.value, sec: id, attrs: `data-extra="${i}"` })}
          <button class="icon-btn boxed" type="button" aria-label="${t("form.removeField")}" data-action="remove-extra" data-sec="${id}" data-extra="${i}">${icon("close", 16, 'stroke="currentColor" stroke-width="2"')}</button></div>`).join("")}
        <div><button class="btn" type="button" data-action="add-extra" data-sec="${id}">${icon("plus", 14, 'stroke="currentColor" stroke-width="2.25"')}${t("form.addField")}</button></div>`;
    case "custom":
      return input("title", t("form.sectionTitle"), { value: s.title, sec: id, ph: t("ph.sectionTitle") })
        + input("content", t("form.content"), { value: s.content, sec: id, ph: t("ph.content"), area: 4 });
  }
}

function renderForm() {
  const f = form;
  const regular = f.type === "regular";
  const editing = Boolean(f.id);
  const present = new Set(f.sections.map((s) => s.kind));
  const options = SECTION_KINDS
    .filter((k) => (regular || !["offerLink", "keyPoints"].includes(k)) && (k === "custom" || !present.has(k)))
    .map((k) => `<button class="option" type="button" data-add="${k}"><strong>${t("section." + k)}</strong><span>${t("desc." + k)}</span></button>`)
    .join("");
  const last = f.sections.length - 1;
  const stroke2 = 'stroke="currentColor" stroke-width="2"';
  const sections = f.sections.map((s, i) => {
    const title = t("section." + s.kind);
    return `<section class="mod" aria-label="${title}">
      <div class="mod-head">${GRIP}<h2>${title}</h2>
        <button class="icon-btn" type="button" aria-label="${t("form.moveUp", { title })}" data-action="move" data-sec="${s.id}" data-dir="-1" ${i === 0 ? "disabled" : ""}>${icon("up", 16, stroke2)}</button>
        <button class="icon-btn" type="button" aria-label="${t("form.moveDown", { title })}" data-action="move" data-sec="${s.id}" data-dir="1" ${i === last ? "disabled" : ""}>${icon("chevron", 16, stroke2)}</button>
        <button class="icon-btn" type="button" aria-label="${t("form.remove", { title })}" data-action="remove" data-sec="${s.id}">${icon("close", 16, stroke2)}</button>
      </div>
      <div class="mod-body">${sectionBody(s)}</div></section>`;
  }).join("");
  const typeLabel = t(regular ? "type.regular" : "type.spontaneous");
  const busy = f.ai === "loading" ? "disabled" : "";

  view.innerHTML = `<form class="narrow" id="app-form" novalidate>
    ${editing ? backLink(`#/a/${f.id}`, t("back.application"))
      : `<button class="back" type="button" data-action="change-type">${icon("back", 14, stroke2)}${t("form.changeType")}</button>`}
    <header class="stack">
      <div class="eyebrow">${editing ? typeLabel : t("form.step", { type: typeLabel })}</div>
      <h1>${t(editing ? "form.editTitle" : "form.newTitle")}</h1>
      <p class="lead">${t(editing ? "form.editLead" : "form.newLead")}</p>
    </header>
    <section class="mod" aria-labelledby="h-basics">
      <div class="mod-head"><h2 id="h-basics">${t("form.basics")}</h2></div>
      <div class="mod-body"><div class="fields">
        ${input("company", t("form.company"), { value: f.company, ph: t("ph.company"), attrs: `required ${busy}` })}
        ${input("jobTitle", t(regular ? "form.jobTitle" : "form.aimedPosition"), { value: f.jobTitle, ph: t(regular ? "ph.jobTitle" : "ph.aimedPosition"), attrs: busy })}
        <label class="lbl"><span>${t("form.status")}</span><select class="field" data-key="status">
          ${STATUSES.map((s) => `<option value="${s}" ${s === f.status ? "selected" : ""}>${t("status." + s)}</option>`).join("")}
        </select></label>
      </div></div>
    </section>
    ${sections}
    <div class="menu-wrap" style="align-self:flex-start">
      <button class="btn btn-accent" type="button" data-action="menu" aria-haspopup="true" aria-expanded="${f.menuOpen}">${icon("plus", 16, 'stroke="currentColor" stroke-width="2.25"')}${t("form.addSection")}</button>
      ${f.menuOpen && options ? `<div class="menu left" role="group" aria-label="${t("form.addGroup")}">${options}</div>` : ""}
    </div>
    ${f.error ? `<p class="banner error" role="status">${esc(f.error)}</p>` : ""}
    <div class="form-foot">
      ${editing ? `<button class="btn btn-danger" type="button" data-action="delete">${t("form.delete")}</button>` : ""}
      <div class="actions">
        <a class="btn" href="${editing ? `#/a/${f.id}` : "#/"}">${t("form.cancel")}</a>
        <button class="btn btn-primary" type="submit" ${f.saving ? "disabled" : ""}>${t(editing ? "form.saveChanges" : "form.save")}</button>
      </div>
    </div></form>`;

  view.oninput = onFormInput;
  view.onchange = onFormChange;
  view.onclick = onFormClick;
  view.onsubmit = (e) => {
    e.preventDefault();
    saveForm();
  };
  view.ondragover = (e) => {
    const zone = e.target.closest("[data-drop]");
    if (zone) {
      e.preventDefault();
      zone.classList.add("over");
    }
  };
  view.ondragleave = (e) => e.target.closest("[data-drop]")?.classList.remove("over");
  view.ondrop = (e) => {
    const zone = e.target.closest("[data-drop]");
    if (!zone) return;
    e.preventDefault();
    setFile(zone.dataset.drop, e.dataTransfer.files[0]);
  };
}

function findSection(id) {
  return form.sections.find((s) => s.id === id);
}

function onFormInput(e) {
  const { key, sec, extra } = e.target.dataset;
  if (!key) return;
  if (!sec) {
    form[key] = e.target.value;
    return;
  }
  const s = findSection(sec);
  if (extra !== undefined) s.extra[extra][key] = e.target.value;
  else s[key] = e.target.value;
  if ("filledByAi" in s && key !== "why") s.filledByAi = false;
}

function onFormChange(e) {
  if (e.target.dataset.file) setFile(e.target.dataset.file, e.target.files[0]);
}

function setFile(sectionId, file) {
  if (!file) return;
  findSection(sectionId)._pending = file;
  renderForm();
}

function onFormClick(e) {
  const add = e.target.closest("[data-add]");
  if (add) {
    form.sections.push(newSection(add.dataset.add));
    form.menuOpen = false;
    return renderForm();
  }
  const el = e.target.closest("[data-action]");
  if (!el) return;
  const s = el.dataset.sec && findSection(el.dataset.sec);
  const list = form.sections;
  switch (el.dataset.action) {
    case "change-type":
      form = null;
      return renderTypeStep();
    case "menu":
      form.menuOpen = !form.menuOpen;
      break;
    case "with-company":
      form.withCompany = el.checked;
      break;
    case "move": {
      const i = list.indexOf(s);
      const j = i + Number(el.dataset.dir);
      [list[i], list[j]] = [list[j], list[i]];
      break;
    }
    case "remove":
      list.splice(list.indexOf(s), 1);
      break;
    case "add-extra":
      s.extra.push({ label: "", value: "" });
      break;
    case "remove-extra":
      s.extra.splice(Number(el.dataset.extra), 1);
      break;
    case "choose":
      return el.previousElementSibling.click();
    case "fetch":
      return fetchOffer();
    case "delete":
      return deleteApplication();
  }
  renderForm();
}

async function fetchOffer() {
  const link = section(form, "offerLink");
  const kp = section(form, "keyPoints");
  if (!link.url.trim() && !link.paste.trim()) {
    Object.assign(form, { ai: "error", aiError: t("ai.needInput") });
    return renderForm();
  }
  const co = form.withCompany && section(form, "company");
  const edited = (kp && !kp.filledByAi && [...KEY_FIELDS, ...KEY_LISTS].some((k) => kp[k].trim()))
    || (co && !co.filledByAi && co.summary.trim());
  if (edited && !confirm(t("ai.confirmReplace"))) return;
  form.ai = "loading";
  renderForm();
  try {
    const r = await api("/api/offer/summary", { method: "POST", body: { url: link.url, text: link.paste, withCompany: Boolean(form.withCompany) } });
    Object.assign(link, { rawText: r.rawText, fetchedAt: new Date().toISOString() });
    if (kp) {
      for (const k of KEY_FIELDS) kp[k] = r[k];
      for (const k of KEY_LISTS) kp[k] = r[k].join("\n");
      kp.filledByAi = true;
    }
    if (form.withCompany && r.companySummary) {
      if (!section(form, "company")) form.sections.push(newSection("company"));
      Object.assign(section(form, "company"), { summary: r.companySummary, filledByAi: true });
    }
    if (!form.company.trim()) form.company = r.company;
    if (!form.jobTitle.trim()) form.jobTitle = r.jobTitle;
    Object.assign(form, { ai: "done", aiSource: r.source || t("ai.pastedText") });
  } catch (err) {
    Object.assign(form, { ai: "error", aiError: err.status === 422 ? t("ai.unreadable") : err.message });
  }
  renderForm();
}

async function saveForm() {
  const f = form;
  if (!f.company.trim()) {
    f.error = t("form.companyRequired");
    return renderForm();
  }
  Object.assign(f, { saving: true, error: "" });
  renderForm();
  try {
    for (const s of f.sections) {
      if (!s._pending) continue;
      s.file = await api(`/api/files?name=${encodeURIComponent(s._pending.name)}`, { method: "POST", body: s._pending });
      delete s._pending;
    }
    const sections = f.sections.map(({ _pending, paste, ...s }) => {
      if (s.kind === "offerLink" && paste?.trim()) s.rawText = paste.trim();
      if (s.kind === "keyPoints") for (const k of KEY_LISTS) s[k] = s[k].split("\n").map((l) => l.trim()).filter(Boolean);
      return s;
    });
    const body = { type: f.type, company: f.company.trim(), jobTitle: f.jobTitle.trim(), status: f.status, sections };
    const saved = f.id
      ? await api(`/api/applications/${f.id}`, { method: "PUT", body })
      : await api("/api/applications", { method: "POST", body });
    form = null;
    location.hash = `#/a/${saved.id}`;
    loadApps().catch(() => {});
  } catch (err) {
    Object.assign(f, { saving: false, error: err.message });
    renderForm();
  }
}

async function deleteApplication() {
  if (!confirm(t("form.confirmDelete"))) return;
  try {
    await api(`/api/applications/${form.id}`, { method: "DELETE" });
    form = null;
    location.hash = "#/";
  } catch (err) {
    form.error = err.message;
    renderForm();
  }
}

// ---------- Recherche d'offres ----------

const search = { params: { q: "", location: "", department: "", kind: "emploi" }, data: null, loading: false, error: "" };
let found = [];

function showOfferSearch() {
  view.className = "list";
  rerender = renderOfferSearch;
  renderOfferSearch();
}

function resultCard(o, i) {
  const meta = [o.company, o.location, o.contract_type, o.salary, o.published].filter(Boolean).join(" · ");
  return `<section class="card"><div class="card-head"><h2>${esc(o.title)}</h2><span class="meta">${esc(o.source)}</span></div>
    <div class="card-body">
      ${meta ? `<p class="meta">${esc(meta)}</p>` : ""}
      ${o.description || o.snippet ? `<p class="prose scroll">${esc(o.description || o.snippet)}</p>` : ""}
      <div class="actions">
        <a class="btn" href="${esc(o.url)}" target="_blank" rel="noopener">${t("search.view")}</a>
        <button class="btn btn-accent" type="button" data-track="${i}">${t("search.track")}</button>
      </div>
    </div></section>`;
}

function renderOfferSearch() {
  const p = search.params;
  const d = search.data;
  let results = "";
  if (d) {
    found = [...d.offers.map((o) => ({ ...o, source: "France Travail" })), ...d.web.map((o) => ({ ...o, source: hostOf(o.url) }))];
    const notes = [d.error && t("search.ftError", { error: d.error }), d.web_error && t("search.webError", { error: d.web_error })].filter(Boolean);
    results = `
      <p class="links">${t("search.alsoOn")} ${d.links.map((l) => `<a class="link" href="${esc(l.url)}" target="_blank" rel="noopener">${esc(l.name)}</a>`).join("")}</p>
      ${notes.map((n) => `<p class="banner neutral">${esc(n)}</p>`).join("")}
      <div class="results">${found.map(resultCard).join("") || `<p class="empty">${t("search.none")}</p>`}</div>`;
  }
  view.innerHTML = `
    <h1>${t("nav.offers")}</h1>
    <form class="mod" id="search-form"><div class="mod-body"><div class="fields">
      ${input("q", t("search.keywords"), { value: p.q, ph: t("ph.keywords") })}
      ${input("location", t("search.location"), { value: p.location, ph: "Lyon" })}
      ${input("department", t("search.department"), { value: p.department, ph: "69", attrs: 'maxlength="3"' })}
      <label class="lbl"><span>${t("search.kind")}</span><select class="field" data-key="kind">
        ${["emploi", "stage", "alternance"].map((k) => `<option value="${k}" ${k === p.kind ? "selected" : ""}>${t("kind." + k)}</option>`).join("")}
      </select></label>
      <button class="btn btn-primary" type="submit" ${search.loading ? "disabled" : ""}>${t("search.submit")}</button>
    </div></div></form>
    ${search.loading ? `<div class="banner loading" role="status"><span>${t("search.loading")}</span><div class="progress"></div></div>` : ""}
    ${search.error ? `<p class="banner error" role="status">${esc(search.error)}</p>` : ""}
    ${results}`;

  view.oninput = view.onchange = (e) => {
    if (e.target.dataset.key) p[e.target.dataset.key] = e.target.value;
  };
  view.onsubmit = async (e) => {
    e.preventDefault();
    Object.assign(search, { loading: true, error: "" });
    renderOfferSearch();
    try {
      search.data = await api(`/api/jobs?${new URLSearchParams(p)}`);
    } catch (err) {
      search.error = err.message;
    }
    search.loading = false;
    if (location.hash.startsWith("#/offers")) renderOfferSearch();
  };
  view.onclick = (e) => {
    const track = e.target.closest("[data-track]");
    if (!track) return;
    const o = found[track.dataset.track];
    prefill = { company: o.company || "", jobTitle: o.title, url: o.url, rawText: o.description || "" };
    location.hash = "#/new";
  };
}

function hostOf(url) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "";
  }
}

// ---------- Connexion ----------

function onAuth(user) {
  const id = user ? user.uid : null;
  if (id === userId) return; // simple renouvellement du jeton
  userId = id;
  apps = [];
  appsLoaded = false;
  route();
  if (userId && location.hash.split("/")[1]) loadApps().catch(() => {}); // Box charge déjà la liste
}

function showLogin() {
  rerender = showLogin;
  view.innerHTML = `
    <h1>${t("auth.title")}</h1>
    <form class="login">
      <label class="lbl"><span>${t("auth.email")}</span><input class="field" type="email" name="email" required autocomplete="email"></label>
      <label class="lbl"><span>${t("auth.password")}</span><input class="field" type="password" name="password" required minlength="6" autocomplete="current-password"></label>
      <div class="fields">
        <button class="btn btn-primary" name="signIn">${t("auth.signIn")}</button>
        <button class="btn" name="signUp">${t("auth.signUp")}</button>
      </div>
      <button type="button" class="btn" data-google>${t("auth.google")}</button>
      <p class="banner error" role="status" hidden></p>
    </form>`;
  const error = view.querySelector(".banner");
  const attempt = (promise) => promise.catch((err) => {
    error.textContent = err.message;
    error.hidden = false;
  });
  view.onsubmit = (e) => {
    e.preventDefault();
    const { email, password } = e.target.elements;
    attempt(authApi[e.submitter.name](email.value, password.value));
  };
  view.onclick = (e) => {
    if (e.target.closest("[data-google]")) attempt(authApi.google());
  };
}
