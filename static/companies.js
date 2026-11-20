// Page « Trouver des entreprises » : entreprises du secteur dans un rayon donné, contact publié
// sur leur site, e-mail de candidature spontanée et ajout à la Box.

const SIZE_RANGES = {
  "00": "0", "01": "1–2", "02": "3–5", "03": "6–9", 11: "10–19", 12: "20–49", 21: "50–99", 22: "100–199",
  31: "200–249", 32: "250–499", 41: "500–999", 42: "1000–1999", 51: "2000–4999", 52: "5000–9999", 53: "10000+",
};
const RADII = [2, 5, 10, 20, 30, 50];
const MIN_SIZES = [0, 1, 10, 50, 250];

const finder = {
  form: null, // { what, where, radius, minSize }
  data: null, // dernière réponse : center, activities, results, page, hasMore
  results: [],
  loading: false,
  error: "",
  items: {}, // état par SIREN : contact, e-mail rédigé, ajout à la Box
};

function sizeLabel(code) {
  return SIZE_RANGES[code] ? t("company.size", { n: SIZE_RANGES[code] }) : "";
}

function normName(text) {
  return (text || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
}

function inBox(company) {
  const name = normName(company.name);
  return apps.some((a) => normName(a.company) === name);
}

async function showCompanies() {
  view.className = "";
  rerender = renderCompanies;
  if (!finder.form) {
    finder.form = { what: "", where: "", radius: 10, minSize: 1 };
    try {
      const p = await api("/api/profile");
      Object.assign(finder.form, { what: p.target || "", where: p.location || "" });
    } catch {}
  }
  if (!appsLoaded) loadApps().catch(() => {});
  renderCompanies();
}

async function runCompanySearch({ more = false, activities = null } = {}) {
  const f = finder.form;
  if (!f.what.trim() || !f.where.trim()) {
    finder.error = t("company.needInput");
    return renderCompanies();
  }
  Object.assign(finder, { loading: true, error: "" });
  if (!more) finder.results = [];
  renderCompanies();
  try {
    const body = {
      what: f.what, where: f.where, radius: Number(f.radius), minSize: Number(f.minSize),
      page: more ? finder.data.page + 1 : 1,
      activities: activities || (more ? finder.data.activities.map((a) => a.code) : []),
    };
    const data = await api("/api/companies/search", { method: "POST", body });
    finder.data = data;
    const known = new Set(finder.results.map((r) => r.siren));
    finder.results.push(...data.results.filter((r) => !known.has(r.siren)));
  } catch (err) {
    finder.error = err.message;
  }
  finder.loading = false;
  if (location.hash.startsWith("#/companies")) renderCompanies();
}

function companyResultCard(c) {
  const st = finder.items[c.siren] || {};
  const meta = [c.activityLabel || c.activity, sizeLabel(c.sizeCode), t("company.distance", { km: c.distanceKm.toLocaleString(LOCALES[lang]) })]
    .filter(Boolean).join(" · ");
  let contact = "";
  if (st.contactLoading) {
    contact = `<div class="banner loading" role="status"><span>${t("company.contactLoading")}</span><div class="progress"></div></div>`;
  } else if (st.contactError) {
    contact = `<p class="banner error" role="status">${esc(st.contactError)}</p>`;
  } else if (st.contact) {
    const k = st.contact;
    const emails = k.emails.map((e, i) => `<label class="check"><input type="radio" name="to-${c.siren}" value="${esc(e.email)}" data-pick-email="${c.siren}" ${e.email === st.to ? "checked" : ""}>
      <span>${esc(e.email)} <span class="meta">· ${t("emailKind." + e.kind)}</span></span></label>`).join("");
    contact = `<div class="contact-box">
      ${k.website ? `<p>${t("company.website")} <a class="link" href="${esc(k.website)}" target="_blank" rel="noopener">${esc(hostOf(k.website))}</a>
        ${k.careersUrl ? ` · <a class="link" href="${esc(k.careersUrl)}" target="_blank" rel="noopener">${t("company.careers")}</a>` : ""}</p>` : `<p class="meta">${t("company.noWebsite")}</p>`}
      ${emails ? `<div class="stack">${emails}</div><p class="help">${t("company.emailsHelp")}</p>` : k.website ? `<p class="meta">${t("company.noEmail")}</p>` : ""}
    </div>`;
  }
  let draft = "";
  if (st.writing) {
    draft = `<div class="banner loading" role="status"><span>${t("company.writing")}</span><div class="progress"></div></div>`;
  } else if (st.writeError) {
    draft = `<p class="banner error" role="status">${esc(st.writeError)}</p>`;
  } else if (st.email) {
    const mailto = `mailto:${encodeURIComponent(st.to || "")}?subject=${encodeURIComponent(st.email.subject)}&body=${encodeURIComponent(st.email.body)}`;
    draft = `<div class="stack">
      ${input("to", t("form.sentTo"), { type: "email", value: st.to || "", sec: c.siren, ph: "recrutement@…" })}
      ${input("subject", t("form.subject"), { value: st.email.subject, sec: c.siren })}
      ${input("body", t("form.message"), { value: st.email.body, sec: c.siren, area: 10 })}
      <p class="help">${t("company.attachCv")}</p>
      <div class="actions">
        <a class="btn btn-primary" href="${mailto}" data-mailto="${c.siren}">${icon("mail")}${t("company.openMail")}</a>
        <button class="btn" type="button" data-copy-mail="${c.siren}">${t(st.copied ? "common.copied" : "common.copy")}</button>
        <button class="btn btn-accent" type="button" data-add-box="${c.siren}" ${st.added || st.adding ? "disabled" : ""}>${t(st.added ? "company.added" : "company.addBox")}</button>
      </div></div>`;
  }
  const known = inBox(c) || st.added;
  return `<section class="card"><div class="card-head"><h2 class="company-name">${esc(c.name)}</h2>
      ${known ? `<span class="next-tag">${t("company.inBox")}</span>` : ""}</div>
    <div class="card-body">
      <p class="meta">${esc(meta)}</p>
      <p class="meta">${esc(c.address)}${c.legalName && normName(c.legalName) !== normName(c.name) ? ` · ${esc(c.legalName)}` : ""}</p>
      ${contact}
      <div class="actions">
        ${st.contact || st.contactLoading ? "" : `<button class="btn" type="button" data-contact="${c.siren}">${icon("search")}${t("company.findContact")}</button>`}
        ${st.email || st.writing ? "" : `<button class="btn btn-accent" type="button" data-write="${c.siren}">${icon("spark")}${t("company.write")}</button>`}
      </div>
      ${draft}
    </div></section>`;
}

function renderCompanies() {
  const f = finder.form;
  if (!f) return;
  const d = finder.data;
  const busy = finder.loading ? "disabled" : "";
  const chips = d ? d.activities.map((a) => `<span class="chip">${esc(a.label)} <span class="meta">${a.code}</span>
    ${d.activities.length > 1 ? `<button type="button" class="chip-x" aria-label="${t("company.removeSector", { label: esc(a.label) })}" data-drop-sector="${a.code}" ${busy}>${icon("close", 12, 'stroke="currentColor" stroke-width="2.5"')}</button>` : ""}</span>`).join("") : "";
  view.innerHTML = `<div class="narrow">
    <header class="stack"><h1>${t("nav.companies")}</h1><p class="lead">${t("company.lead")}</p></header>
    <form class="mod" id="company-form"><div class="mod-body">
      <div class="fields">
        ${input("what", t("company.what"), { value: f.what, ph: t("company.whatPh"), attrs: busy })}
        ${input("where", t("company.where"), { value: f.where, ph: t("company.wherePh"), attrs: busy })}
      </div>
      <div class="fields">
        <label class="lbl"><span>${t("company.radius")}</span><select class="field" data-key="radius" ${busy}>
          ${RADII.map((r) => `<option value="${r}" ${Number(f.radius) === r ? "selected" : ""}>${r} km</option>`).join("")}</select></label>
        <label class="lbl"><span>${t("company.minSize")}</span><select class="field" data-key="minSize" ${busy}>
          ${MIN_SIZES.map((n) => `<option value="${n}" ${Number(f.minSize) === n ? "selected" : ""}>${t("company.minSize" + n)}</option>`).join("")}</select></label>
        <button class="btn btn-primary" type="submit" ${busy}>${icon("search")}${t("company.search")}</button>
      </div>
    </div></form>
    ${d ? `<div class="stack"><p class="meta">${t("company.sectors", { place: esc(d.center.label) })}</p><div class="chips">${chips}</div></div>` : ""}
    ${finder.error ? `<p class="banner error" role="status">${esc(finder.error)}</p>` : ""}
    ${finder.loading && !finder.results.length ? `<div class="banner loading" role="status"><span>${t("company.searching")}</span><div class="progress"></div></div>` : ""}
    ${d && !finder.results.length && !finder.loading ? `<p class="empty">${t("company.none")}</p>` : ""}
    <div class="results">${finder.results.map(companyResultCard).join("")}</div>
    ${d?.hasMore ? `<div class="actions"><button class="btn" type="button" data-more ${busy}>${t(finder.loading ? "company.searching" : "company.more")}</button></div>` : ""}
  </div>`;

  view.oninput = view.onchange = (e) => {
    const { key, sec } = e.target.dataset;
    if (e.target.dataset.pickEmail) {
      finder.items[e.target.dataset.pickEmail].to = e.target.value;
      return renderCompanies();
    }
    if (!key) return;
    if (sec) {
      const st = finder.items[sec];
      if (key === "to") st.to = e.target.value;
      else st.email[key] = e.target.value;
      const link = view.querySelector(`[data-mailto="${sec}"]`);
      if (link) link.href = `mailto:${encodeURIComponent(st.to || "")}?subject=${encodeURIComponent(st.email.subject)}&body=${encodeURIComponent(st.email.body)}`;
    } else {
      f[key] = e.target.value;
    }
  };
  view.onsubmit = (e) => {
    e.preventDefault();
    finder.items = {};
    runCompanySearch();
  };
  view.onclick = async (e) => {
    const el = (sel) => e.target.closest(sel);
    if (el("[data-more]")) return runCompanySearch({ more: true });
    const drop = el("[data-drop-sector]");
    if (drop) {
      return runCompanySearch({ activities: finder.data.activities.map((a) => a.code).filter((c) => c !== drop.dataset.dropSector) });
    }
    const target = el("[data-contact],[data-write],[data-copy-mail],[data-add-box],[data-mailto]");
    if (!target) return;
    const siren = Object.values(target.dataset)[0];
    const c = finder.results.find((r) => r.siren === siren);
    const st = (finder.items[siren] ||= {});
    if (target.dataset.contact) await findContact(c, st);
    else if (target.dataset.write) await writeSpontaneous(c, st);
    else if (target.dataset.copyMail) {
      await navigator.clipboard.writeText(`${st.email.subject}\n\n${st.email.body}`).catch(() => {});
      st.copied = true;
    } else if (target.dataset.addBox) await addToBox(c, st);
    else if (target.dataset.mailto) return track("spontaneous_opened");
    renderCompanies();
  };
}

async function findContact(c, st) {
  Object.assign(st, { contactLoading: true, contactError: "" });
  renderCompanies();
  try {
    st.contact = await api("/api/companies/contact", { method: "POST", body: { name: c.name, city: c.city } });
    st.to ||= st.contact.emails[0]?.email || "";
  } catch (err) {
    st.contactError = err.message;
  }
  st.contactLoading = false;
}

async function writeSpontaneous(c, st) {
  Object.assign(st, { writing: true, writeError: "" });
  renderCompanies();
  try {
    const company = { name: c.name, city: c.city, activity: c.activity, activityLabel: c.activityLabel, sizeLabel: sizeLabel(c.sizeCode) };
    st.email = await api("/api/companies/application", {
      method: "POST", body: { company, what: finder.form.what, description: st.contact?.description || "", lang },
    });
  } catch (err) {
    st.writeError = err.message;
  }
  st.writing = false;
}

async function addToBox(c, st) {
  st.adding = true;
  renderCompanies();
  const sections = [
    { id: "s-email", kind: "email", to: st.to || "", sentAt: "", subject: st.email.subject, body: st.email.body },
    { id: "s-company", kind: "company", summary: [c.activityLabel, c.address, st.contact?.website].filter(Boolean).join("\n"), why: "" },
  ];
  if (st.to) sections.push({ id: "s-contact", kind: "contact", name: "", position: "", email: st.to, phone: "", extra: [] });
  try {
    await api("/api/applications", {
      method: "POST", body: { type: "spontaneous", company: c.name, jobTitle: finder.form.what, status: "notsent", sections },
    });
    st.added = true;
    loadApps().catch(() => {});
  } catch (err) {
    st.writeError = err.message;
  }
  st.adding = false;
}
