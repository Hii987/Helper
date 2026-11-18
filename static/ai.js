// Fonctions IA rebranchées de Helper : réponses de recruteurs, préparation d'entretien,
// assistant de recherche, rédaction (lettre, CV, e-mails) et profil.

const REPLY_TYPES = ["entretien", "test", "offre", "demande_infos", "refus", "autre"];
const EMAIL_GOALS = ["reply", "accept", "decline", "followup", "thanks"];

// ---------- Rendu Markdown minimal (titres, listes, tableaux, citations, gras, liens) ----------

function renderMarkdown(text) {
  const inline = (line) =>
    esc(line.replace(/<(https?:\/\/[^\s>]+)>/g, "$1"))
      .replace(/&#60;br\s*\/?&#62;/gi, "<br>")
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)&]+)\)/g, '<a class="link" href="$2" target="_blank" rel="noopener">$1</a>')
      .replace(/(^|[\s(])(https?:\/\/[^\s)&<]+)/g, '$1<a class="link" href="$2" target="_blank" rel="noopener">$2</a>');
  const cells = (line) => line.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
  const lines = (text || "").split("\n");
  let html = "";
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trimEnd();
    if (line.trim().startsWith("|") && /^\s*\|?\s*:?-{2,}/.test(lines[i + 1] || "")) {
      html += "<div class='md-table'><table><thead><tr>" + cells(line).map((c) => `<th>${inline(c)}</th>`).join("") + "</tr></thead><tbody>";
      i += 2;
      while (i < lines.length && lines[i].trim().startsWith("|")) {
        html += "<tr>" + cells(lines[i]).map((c) => `<td>${inline(c)}</td>`).join("") + "</tr>";
        i++;
      }
      html += "</tbody></table></div>";
      i--;
      continue;
    }
    const item = line.match(/^\s*(?:[-*•]|\d+[.)])\s+(.*)/);
    if (item) {
      html = (html.endsWith("</ul>") ? html.slice(0, -5) : html + "<ul>") + `<li>${inline(item[1])}</li></ul>`;
      continue;
    }
    const heading = line.match(/^(#{1,4})\s+(.*)/);
    const quote = line.match(/^\s*>\s?(.*)/);
    if (heading) html += `<h3>${inline(heading[2])}</h3>`;
    else if (/^\s*(-{3,}|\*{3,})\s*$/.test(line)) html += "<hr>";
    else if (quote) html += `<blockquote>${inline(quote[1])}</blockquote>`;
    else if (line.trim()) html += `<p>${inline(line)}</p>`;
  }
  return `<div class="md">${html}</div>`;
}

function outputBlock(text) {
  return `<div class="output">${renderMarkdown(text)}</div>
    <div class="actions"><button class="btn" type="button" data-copy>${t("common.copy")}</button></div>`;
}

function copyOnClick(e, text) {
  const btn = e.target.closest("[data-copy]");
  if (!btn) return false;
  navigator.clipboard.writeText(text).then(() => (btn.textContent = t("common.copied")));
  return true;
}

// ---------- Prochaine étape (Box et page candidature) ----------

function nextStepLabel(n) {
  return t("next." + (n.kind || "todo"), { date: fmtDate(n.date) });
}

function nextStepTag(a) {
  const n = a.nextStep;
  if (!n?.date || a.status === "refused") return "";
  const late = n.date < new Date().toISOString().slice(0, 10);
  return `<span class="next-tag${late ? " late" : ""}">${esc(nextStepLabel(n))}</span>`;
}

function nextStepBanner(app) {
  const n = app.nextStep;
  if (!n?.date || app.status === "refused") return "";
  return `<div class="banner next" role="status"><strong>${esc(nextStepLabel(n))}</strong>${n.label ? `<span>${esc(n.label)}</span>` : ""}</div>`;
}

// ---------- Préparation d'entretien ----------

function prepCard(app, prep) {
  const p = app.prep;
  const button = `<button class="btn ${p ? "" : "btn-primary"}" type="button" data-prep ${prep.loading ? "disabled" : ""}>${icon("spark")}${t(p ? "prep.regenerate" : "prep.generate")}</button>`;
  let body;
  if (prep.loading) {
    body = `<div class="banner loading" role="status"><span>${t("prep.loading")}</span><div class="progress"></div></div>`;
  } else if (p) {
    body = `<p class="meta">${t("prep.generatedOn", { date: fmtDate(p.at) })}</p>${renderMarkdown(p.text)}
      <div class="actions">${button}<button class="btn" type="button" data-copy-prep>${t("common.copy")}</button></div>`;
  } else {
    body = `<p class="help">${t("prep.help")}</p><div class="actions">${button}</div>`;
  }
  const error = prep.error ? `<p class="banner error" role="status">${esc(prep.error)}</p>` : "";
  return `<section class="card prep" id="prep"><div class="card-head"><h2>${t("prep.title")}</h2></div><div class="card-body">${error}${body}</div></section>`;
}

async function runPrep(app, prep, redraw) {
  Object.assign(prep, { loading: true, error: "" });
  redraw();
  try {
    return await api(`/api/applications/${app.id}/prep`, { method: "POST", body: { lang } });
  } catch (err) {
    prep.error = err.message;
    return null;
  } finally {
    prep.loading = false;
  }
}

// ---------- Historique des réponses ----------

function repliesCard(app) {
  const list = app.replies || [];
  if (!list.length) return "";
  const items = list.map((r) => {
    const when = [r.date && fmtDate(r.date), r.time, r.format].filter(Boolean).join(" · ");
    return `<li class="reply-item">
      <div class="reply-head"><span class="type-tag">${t("replyType." + r.type)}</span><span class="meta">${t("reply.received", { date: fmtDate(r.at) })}</span></div>
      ${r.summary ? `<p>${esc(r.summary)}</p>` : ""}
      ${when ? `<p class="meta">${esc(when)}</p>` : ""}
      ${r.todo ? `<p class="meta"><strong>${t("reply.todo")}</strong> ${esc(r.todo)}</p>` : ""}
      <details><summary class="link">${t("reply.fullMessage")}</summary><div class="prose">${paras(r.message || "")}</div></details>
    </li>`;
  }).join("");
  return card(t("reply.history"), `<ul class="reply-list">${items}</ul>`);
}

// ---------- Page « Réponse d'un recruteur » ----------

const replyState = { message: "", applicationId: "", loading: "", error: "", result: null };

async function showReply(appId = "") {
  view.className = "";
  Object.assign(replyState, { applicationId: appId || "", error: "", result: null, loading: "" });
  rerender = renderReply;
  renderReply();
  if (!appsLoaded) {
    await loadApps().catch(() => {});
    renderReply();
  }
}

function renderReply() {
  const s = replyState;
  const options = apps.map((a) => `<option value="${a.id}" ${a.id === s.applicationId ? "selected" : ""}>${esc(a.company)}${a.jobTitle ? " — " + esc(a.jobTitle) : ""}</option>`).join("");
  const r = s.result;
  const result = r ? `
    <section class="card key"><div class="card-head"><h2>${t("replyType." + r.analysis.type_reponse)}</h2></div><div class="card-body">
      <p>${t(r.created ? "reply.created" : "reply.updated", { company: esc(r.application.company) })} ${statusTag(r.application.status)}</p>
      ${r.analysis.resume ? `<p>${esc(r.analysis.resume)}</p>` : ""}
      ${nextStepBanner(r.application)}
      ${r.analysis.a_faire ? `<p><strong>${t("reply.todo")}</strong> ${esc(r.analysis.a_faire)}</p>` : ""}
      <div class="actions">
        <a class="btn btn-primary" href="#/a/${r.application.id}">${t("reply.open")}</a>
        <a class="btn" href="#/write/email/${r.application.id}">${t("write.email")}</a>
      </div>
    </div></section>` : "";
  view.innerHTML = `<div class="narrow">
    ${backLink(s.applicationId ? `#/a/${s.applicationId}` : "#/", t(s.applicationId ? "back.application" : "back.box"))}
    <header class="stack"><h1>${t("reply.title")}</h1><p class="lead">${t("reply.lead")}</p></header>
    <form class="mod" id="reply-form"><div class="mod-body">
      ${input("message", t("reply.message"), { value: s.message, ph: t("reply.messagePh"), area: 10, attrs: s.loading ? "disabled" : "" })}
      <label class="lbl"><span>${t("reply.application")}</span><select class="field" data-key="applicationId" ${s.loading ? "disabled" : ""}>
        <option value="">${t("reply.auto")}</option>${options}</select></label>
      <div class="actions"><button class="btn btn-primary" type="submit" ${s.loading ? "disabled" : ""}>${icon("spark")}${t("reply.submit")}</button></div>
    </div></form>
    ${s.loading ? `<div class="banner loading" role="status"><span>${t(s.loading)}</span><div class="progress"></div></div>` : ""}
    ${s.error ? `<p class="banner error" role="status">${esc(s.error)}</p>` : ""}
    ${result}</div>`;
  view.oninput = view.onchange = (e) => {
    if (e.target.dataset.key) s[e.target.dataset.key] = e.target.value;
  };
  view.onsubmit = async (e) => {
    e.preventDefault();
    if (!s.message.trim()) {
      s.error = t("reply.empty");
      return renderReply();
    }
    Object.assign(s, { loading: "reply.analyzing", error: "", result: null });
    renderReply();
    try {
      const r = await api("/api/replies", { method: "POST", body: { message: s.message, applicationId: s.applicationId } });
      s.message = "";
      loadApps().catch(() => {});
      if (r.prepare) {
        // La préparation se lance sur la page de la candidature, où elle s'affiche.
        sessionStorage.setItem("autoPrep", r.application.id);
        location.hash = `#/a/${r.application.id}`;
        return;
      }
      s.result = r;
    } catch (err) {
      s.error = err.message;
    }
    s.loading = "";
    if (location.hash.split("/")[1] === "reply" || location.hash.endsWith("/reply")) renderReply();
  };
}

// ---------- Assistant ----------

const chat = { history: [], steps: {}, offers: {}, loading: false, error: "", draft: "" };

function showAssistant() {
  view.className = "";
  rerender = renderAssistant;
  renderAssistant();
}

function renderAssistant() {
  const messages = chat.history.map((m, i) => `
    <div class="msg ${m.role}">${m.role === "assistant" ? renderMarkdown(m.content) : `<p>${esc(m.content)}</p>`}</div>
    ${chat.steps[i]?.length ? `<ul class="steps">${chat.steps[i].map((s) => `<li>${esc(s)}</li>`).join("")}</ul>` : ""}
    ${chat.offers[i]?.length ? `<div class="results">${chat.offers[i].map((o, j) => `
      <section class="card"><div class="card-head"><h2>${esc(o.title)}</h2><span class="meta">${esc(o.source === "web" ? hostOf(o.url) : o.source)}</span></div>
      <div class="card-body">${o.snippet ? `<p class="meta">${esc(o.snippet)}</p>` : ""}
        <div class="actions"><a class="btn" href="${esc(o.url)}" target="_blank" rel="noopener">${t("search.view")}</a>
        <button class="btn btn-accent" type="button" data-track-offer="${i}:${j}">${t("search.track")}</button></div></div></section>`).join("")}</div>` : ""}`).join("");
  view.innerHTML = `<div class="narrow">
    <header class="stack"><h1>${t("nav.assistant")}</h1><p class="lead">${t("assistant.lead")}</p></header>
    ${me && !me.profileFilled ? `<p class="banner neutral">${t("common.fillProfile")}</p>` : ""}
    <div class="chat-log">${messages || `<p class="empty">${t("assistant.empty")}</p>`}</div>
    ${chat.loading ? `<div class="banner loading" role="status"><span>${t("assistant.thinking")}</span><div class="progress"></div></div>` : ""}
    ${chat.error ? `<p class="banner error" role="status">${esc(chat.error)}</p>` : ""}
    <form class="chat-form" id="chat-form">
      <textarea class="field" rows="3" data-key="draft" placeholder="${t("assistant.placeholder")}" ${chat.loading ? "disabled" : ""}>${esc(chat.draft)}</textarea>
      <button class="btn btn-primary" type="submit" ${chat.loading ? "disabled" : ""}>${t("assistant.send")}</button>
    </form></div>`;
  view.oninput = (e) => {
    if (e.target.dataset.key === "draft") chat.draft = e.target.value;
  };
  view.onkeydown = (e) => {
    if (e.target.dataset.key === "draft" && e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      document.getElementById("chat-form").requestSubmit();
    }
  };
  view.onclick = (e) => {
    const pick = e.target.closest("[data-track-offer]");
    if (!pick) return;
    const [i, j] = pick.dataset.trackOffer.split(":");
    const o = chat.offers[i][j];
    prefill = { company: o.company || "", jobTitle: o.title, url: o.url, rawText: o.description || o.snippet || "" };
    location.hash = "#/new";
  };
  view.onsubmit = async (e) => {
    e.preventDefault();
    const text = chat.draft.trim();
    if (!text) return;
    chat.history.push({ role: "user", content: text });
    Object.assign(chat, { draft: "", loading: true, error: "" });
    renderAssistant();
    try {
      const r = await api("/api/chat", { method: "POST", body: { messages: chat.history, lang } });
      chat.history.push({ role: "assistant", content: r.text });
      chat.steps[chat.history.length - 1] = r.steps;
      chat.offers[chat.history.length - 1] = r.offers;
    } catch (err) {
      chat.history.pop();
      Object.assign(chat, { draft: text, error: err.message });
    }
    chat.loading = false;
    if (location.hash.startsWith("#/assistant")) {
      renderAssistant();
      view.querySelector(".chat-log").lastElementChild?.scrollIntoView({ block: "nearest" });
    }
  };
}

// ---------- Rédaction : lettre, analyse de CV, e-mails ----------

const writing = { kind: "letter", appId: "", offer: "", company: "", extra: "", received: "", goal: "reply", tone: "", loading: false, error: "", text: "", saved: false };

async function showWrite(kind, appId) {
  view.className = "";
  const fresh = (appId || "") !== writing.appId || (kind && kind !== writing.kind);
  if (fresh) Object.assign(writing, { offer: "", company: "", received: "", extra: "", text: "", error: "", saved: false });
  Object.assign(writing, { kind: ["letter", "cv", "email"].includes(kind) ? kind : writing.kind, appId: appId || "" });
  rerender = renderWrite;
  if (appId && fresh) {
    try {
      const app = await api(`/api/applications/${appId}`);
      writing.app = app;
      writing.company = app.company;
      const link = section(app, "offerLink") || {};
      const kp = section(app, "keyPoints") || {};
      writing.offer = link.rawText || [app.jobTitle, kp.contract, ...(kp.responsibilities || []), ...(kp.requirements || [])].filter(Boolean).join("\n");
      const last = (app.replies || [])[0];
      if (last) {
        writing.received = last.message;
        writing.goal = ["entretien", "test", "offre"].includes(last.type) ? "accept" : last.type === "refus" ? "thanks" : "reply";
      } else {
        writing.goal = "followup";
        writing.received = `${app.jobTitle || ""} — ${app.company}${app.sentAt ? ` (${fmtDate(app.sentAt)})` : ""}`;
      }
    } catch (err) {
      writing.error = err.message;
    }
  }
  renderWrite();
}

function renderWrite() {
  const w = writing;
  const busy = w.loading ? "disabled" : "";
  const tabs = ["letter", "cv", "email"].map((k) => `<a class="tab" href="#/write/${k}${w.appId ? "/" + w.appId : ""}" aria-current="${k === w.kind ? "page" : "false"}">${t("write." + k)}</a>`).join("");
  let fields;
  if (w.kind === "email") {
    fields = `${input("received", t("write.received"), { value: w.received, ph: t("write.receivedPh"), area: 6, attrs: busy })}
      <div class="fields">
        <label class="lbl"><span>${t("write.goal")}</span><select class="field" data-key="goal" ${busy}>
          ${EMAIL_GOALS.map((g) => `<option value="${g}" ${g === w.goal ? "selected" : ""}>${t("goal." + g)}</option>`).join("")}</select></label>
        <label class="lbl"><span>${t("write.tone")}</span><select class="field" data-key="tone" ${busy}>
          ${["", "formel", "concis et direct", "enthousiaste"].map((v, i) => `<option value="${v}" ${v === w.tone ? "selected" : ""}>${t("tone." + i)}</option>`).join("")}</select></label>
      </div>
      ${input("extra", t("write.extra"), { value: w.extra, ph: t("write.extraEmailPh"), attrs: busy })}`;
  } else {
    fields = `${input("offer", t(w.kind === "cv" ? "write.offerOptional" : "write.offer"), { value: w.offer, ph: t("form.pastePh"), area: 8, attrs: busy })}
      ${w.kind === "letter" ? `<div class="fields">${input("company", t("form.company"), { value: w.company, attrs: busy })}
        ${input("extra", t("write.extra"), { value: w.extra, ph: t("write.extraLetterPh"), attrs: busy })}</div>` : ""}`;
  }
  const canSave = w.kind === "letter" && w.appId && w.text && w.app?.type === "regular";
  view.innerHTML = `<div class="narrow">
    ${w.appId ? backLink(`#/a/${w.appId}`, t("back.application")) : ""}
    <header class="stack"><h1>${t("nav.write")}</h1><p class="lead">${t("write.lead")}</p></header>
    <nav class="tabs">${tabs}</nav>
    ${w.kind === "cv" && me && !me.profileFilled ? `<p class="banner neutral">${t("common.fillProfile")}</p>` : ""}
    <form class="mod" id="write-form"><div class="mod-body">${fields}
      <div class="actions"><button class="btn btn-primary" type="submit" ${busy}>${icon("spark")}${t("write.submit." + w.kind)}</button></div>
    </div></form>
    ${w.loading ? `<div class="banner loading" role="status"><span>${t("write.loading")}</span><div class="progress"></div></div>` : ""}
    ${w.error ? `<p class="banner error" role="status">${esc(w.error)}</p>` : ""}
    ${w.text ? outputBlock(w.text) : ""}
    ${canSave ? `<div class="actions"><button class="btn btn-accent" type="button" data-save-letter ${w.saved ? "disabled" : ""}>${t(w.saved ? "write.saved" : "write.saveLetter")}</button></div>` : ""}
  </div>`;
  view.oninput = view.onchange = (e) => {
    if (e.target.dataset.key) w[e.target.dataset.key] = e.target.value;
  };
  view.onclick = async (e) => {
    if (copyOnClick(e, w.text)) return;
    if (!e.target.closest("[data-save-letter]")) return;
    const app = w.app;
    const sections = app.sections.map((s) => (s.kind === "letter" ? { ...s, text: w.text } : s));
    if (!sections.some((s) => s.kind === "letter")) sections.push({ id: `s-letter-${Date.now()}`, kind: "letter", text: w.text });
    try {
      w.app = await api(`/api/applications/${app.id}`, { method: "PUT", body: { type: app.type, company: app.company, jobTitle: app.jobTitle, status: app.status, sections } });
      w.saved = true;
    } catch (err) {
      w.error = err.message;
    }
    renderWrite();
  };
  view.onsubmit = async (e) => {
    e.preventDefault();
    Object.assign(w, { loading: true, error: "", saved: false });
    renderWrite();
    try {
      const body = { kind: w.kind, offer: w.offer, company: w.company, extra: w.extra, received: w.received, goal: w.goal, tone: w.tone, lang };
      w.text = (await api("/api/write", { method: "POST", body })).text;
    } catch (err) {
      w.error = err.message;
    }
    w.loading = false;
    if (location.hash.startsWith("#/write")) renderWrite();
  };
}

// ---------- Profil ----------

const profileState = { data: null, saving: false, notice: "", error: "", importing: false };

async function showProfile() {
  view.className = "";
  rerender = renderProfile;
  Object.assign(profileState, { notice: "", error: "" });
  renderProfile();
  try {
    profileState.data = await api("/api/profile");
  } catch (err) {
    profileState.error = err.message;
  }
  renderProfile();
}

function renderProfile() {
  const p = profileState;
  if (!p.data) {
    view.innerHTML = p.error ? `<p class="banner error">${esc(p.error)}</p>` : "";
    return;
  }
  const d = p.data;
  view.innerHTML = `<form class="narrow" id="profile-form">
    <header class="stack"><h1>${t("nav.profile")}</h1><p class="lead">${t("profile.lead")}</p></header>
    <section class="mod"><div class="mod-head"><h2>${t("profile.about")}</h2></div><div class="mod-body">
      <div class="fields">
        ${input("name", t("form.name"), { value: d.name })}
        ${input("target", t("profile.target"), { value: d.target, ph: t("profile.targetPh") })}
        ${input("location", t("profile.location"), { value: d.location, ph: t("profile.locationPh") })}
      </div>
      ${input("skills", t("profile.skills"), { value: d.skills, ph: t("profile.skillsPh"), area: 3 })}
    </div></section>
    <section class="mod"><div class="mod-head"><h2>${t("profile.cv")}</h2></div><div class="mod-body">
      <div class="drop">${icon("upload", 22, 'stroke="#4B5563" stroke-width="1.5"')}<span>${t(p.importing ? "profile.importing" : "profile.import")}</span>
        <input type="file" accept="application/pdf" hidden data-cv-file>
        <button class="btn" type="button" data-action="choose" ${p.importing ? "disabled" : ""}>${t("form.chooseFile")}</button></div>
      ${input("cv", t("profile.cvText"), { value: d.cv, ph: t("profile.cvPh"), area: 12 })}
    </div></section>
    <section class="mod"><div class="mod-head"><h2>${t("profile.analytics")}</h2></div><div class="mod-body">
      <p class="help">${t("consent.text")}</p>
      <label class="check"><input type="checkbox" data-consent ${me?.analytics === "yes" ? "checked" : ""}>${t("profile.analyticsCheck")}</label>
      <p class="meta">${t("profile.uid", { uid: esc(me?.uid || "") })}</p>
    </div></section>
    ${p.notice ? `<p class="banner success" role="status">${esc(p.notice)}</p>` : ""}
    ${p.error ? `<p class="banner error" role="status">${esc(p.error)}</p>` : ""}
    <div class="form-foot"><div class="actions"><button class="btn btn-primary" type="submit" ${p.saving ? "disabled" : ""}>${t("profile.save")}</button></div></div>
  </form>`;
  view.oninput = (e) => {
    if (e.target.dataset.key) d[e.target.dataset.key] = e.target.value;
  };
  view.onclick = (e) => {
    if (e.target.closest("[data-action=choose]")) view.querySelector("[data-cv-file]").click();
  };
  view.onchange = async (e) => {
    if (e.target.dataset.consent !== undefined) return setConsent(e.target.checked ? "yes" : "no");
    if (e.target.dataset.cvFile === undefined || !e.target.files[0]) return;
    Object.assign(p, { importing: true, error: "", notice: "" });
    renderProfile();
    try {
      const { text } = await api("/api/profile/cv-text", { method: "POST", body: e.target.files[0] });
      d.cv = text;
      p.notice = t(text ? "profile.imported" : "profile.importEmpty");
    } catch (err) {
      p.error = err.message;
    }
    p.importing = false;
    renderProfile();
  };
  view.onsubmit = async (e) => {
    e.preventDefault();
    Object.assign(p, { saving: true, error: "", notice: "" });
    try {
      p.data = await api("/api/profile", { method: "PUT", body: d });
      p.notice = t("profile.saved");
      if (me) me.profileFilled = Boolean(d.cv.trim() || d.skills.trim());
    } catch (err) {
      p.error = err.message;
    }
    p.saving = false;
    renderProfile();
  };
}

// ---------- Consentement aux statistiques ----------

function renderConsent() {
  let bar = document.getElementById("consent");
  const ask = userId && me && !me.analytics;
  if (!ask) return bar?.remove();
  if (!bar) {
    bar = document.createElement("div");
    bar.id = "consent";
    bar.className = "consent";
    bar.setAttribute("role", "dialog");
    bar.setAttribute("aria-label", t("profile.analytics"));
    document.body.append(bar);
    bar.onclick = (e) => {
      const choice = e.target.closest("[data-consent-choice]");
      if (choice) setConsent(choice.dataset.consentChoice);
    };
  }
  bar.innerHTML = `<p>${t("consent.text")}</p>
    <div class="actions"><button class="btn" type="button" data-consent-choice="no">${t("consent.no")}</button>
    <button class="btn btn-primary" type="button" data-consent-choice="yes">${t("consent.yes")}</button></div>`;
}

async function setConsent(choice) {
  try {
    await api("/api/profile/consent", { method: "PUT", body: { analytics: choice } });
    me.analytics = choice;
    tracker.enabled = choice === "yes";
    if (tracker.enabled) track("$pageview", { page: pageName(location.hash) });
  } catch {}
  renderConsent();
}
