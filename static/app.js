const $ = (sel) => document.querySelector(sel);

const STATUS_LABELS = {
  a_postuler: "À postuler",
  postule: "Postulé",
  relance: "Relancé",
  entretien: "Entretien",
  offre: "Offre reçue",
  refuse: "Refusé",
};

// ---------- Utilitaires ----------

function toast(text) {
  const el = $("#toast");
  el.textContent = text;
  el.classList.add("show");
  setTimeout(() => el.classList.remove("show"), 3500);
}

async function api(path, options = {}) {
  const resp = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  if (resp.status === 204) return null;
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(data.detail || `Erreur ${resp.status}`);
  return data;
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text ?? "";
  return div.innerHTML;
}

async function withBusy(button, fn) {
  const label = button.textContent;
  button.disabled = true;
  button.textContent = "Patiente…";
  try {
    await fn();
  } catch (err) {
    toast(err.message);
  } finally {
    button.disabled = false;
    button.textContent = label;
  }
}

function showOutput(el, text) {
  el.innerHTML = "";
  const copy = document.createElement("button");
  copy.className = "secondary small copy-btn";
  copy.textContent = "Copier";
  copy.onclick = () => navigator.clipboard.writeText(text).then(() => toast("Copié !"));
  el.append(copy, document.createTextNode(text));
}

// Rendu Markdown minimal (titres, listes, gras, liens) ; le texte est échappé avant.
function renderMarkdown(text) {
  const inline = (line) =>
    escapeHtml(line)
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/\[([^\]]+)\]\((https?:\/\/[^\s)"'<>]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
      .replace(/(^|[\s(])(https?:\/\/[^\s)"'<>]+)/g, '$1<a href="$2" target="_blank" rel="noopener">$2</a>');
  let html = "";
  let inList = false;
  for (const raw of (text || "").split("\n")) {
    const line = raw.trimEnd();
    const item = line.match(/^\s*(?:[-*•]|\d+[.)])\s+(.*)/);
    if (item) {
      if (!inList) html += "<ul>";
      inList = true;
      html += `<li>${inline(item[1])}</li>`;
      continue;
    }
    if (inList) html += "</ul>";
    inList = false;
    const heading = line.match(/^(#{1,4})\s+(.*)/);
    if (heading) html += `<h${heading[1].length + 1}>${inline(heading[2])}</h${heading[1].length + 1}>`;
    else if (line.trim()) html += `<p>${inline(line)}</p>`;
  }
  return html + (inList ? "</ul>" : "");
}

function switchTab(name) {
  document.querySelectorAll("#tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.id === `tab-${name}`));
  if (name === "tracker") loadApplications();
}

document.querySelectorAll("#tabs button").forEach((b) => (b.onclick = () => switchTab(b.dataset.tab)));

// ---------- Statut ----------

api("/api/status").then((s) => {
  $("#status").innerHTML = `
    <span class="${s.llm ? "ok" : "ko"}">IA Groq ${s.llm ? "connectée" : "non configurée (GROQ_API_KEY)"}</span>
    <span class="${s.france_travail ? "ok" : "ko"}">API France Travail ${s.france_travail ? "connectée" : "non configurée (liens externes uniquement)"}</span>`;
});

// ---------- Assistant (chat) ----------

const chatHistory = [];

function addMessage(role, content) {
  const div = document.createElement("div");
  div.className = `msg ${role}`;
  div.textContent = content;
  $("#chat-log").append(div);
  $("#chat-log").scrollTop = $("#chat-log").scrollHeight;
}

$("#chat-form").onsubmit = (e) => {
  e.preventDefault();
  const input = $("#chat-input");
  const text = input.value.trim();
  if (!text) return;
  input.value = "";
  addMessage("user", text);
  chatHistory.push({ role: "user", content: text });
  withBusy(e.submitter || $("#chat-form button"), async () => {
    const pending = document.createElement("div");
    pending.className = "msg assistant pending";
    pending.textContent = "Je réfléchis et je cherche si besoin…";
    $("#chat-log").append(pending);
    try {
      const { text: answer, steps = [], offers = [], tokens = 0 } = await api("/api/chat", {
        method: "POST",
        body: { messages: chatHistory },
      });
      pending.remove();
      chatHistory.push({ role: "assistant", content: answer });
      if (steps.length || tokens) {
        const div = document.createElement("div");
        div.className = "steps";
        div.innerHTML =
          steps.map((s) => `<div>🔎 ${escapeHtml(s)}</div>`).join("") +
          (tokens ? `<div>≈ ${tokens.toLocaleString("fr-FR")} tokens utilisés</div>` : "");
        $("#chat-log").append(div);
      }
      addMessage("assistant", answer);
      if (offers.length) {
        const div = document.createElement("div");
        div.className = "chat-offers";
        div.innerHTML = `<div class="meta">${offers.length} offre(s) trouvée(s) :</div>` + offers.map(offerCard).join("");
        $("#chat-log").append(div);
        $("#chat-log").scrollTop = $("#chat-log").scrollHeight;
      }
    } catch (err) {
      pending.remove();
      chatHistory.pop();
      throw err;
    }
  });
};

$("#chat-input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    $("#chat-form").requestSubmit();
  }
});

// ---------- Offres (cartes réutilisées par l'assistant et l'onglet Offres) ----------

const offerStore = [];

function offerCard(o) {
  const i = offerStore.push(o) - 1;
  const meta = [o.company, o.location, o.contract_type, o.salary, o.published, o.source && o.source !== "web" ? o.source : hostOf(o.url)]
    .filter(Boolean)
    .join(" · ");
  return `
    <div class="card">
      <h3>${escapeHtml(o.title)}${o.alternance ? '<span class="badge">Alternance</span>' : ""}</h3>
      <div class="meta">${escapeHtml(meta)}</div>
      ${o.description || o.snippet ? `<div class="desc">${escapeHtml(o.description || o.snippet)}</div>` : ""}
      <div class="actions">
        <a href="${escapeHtml(o.url)}" target="_blank" rel="noopener"><button class="small secondary" type="button">Voir l'offre</button></a>
        <button class="small" type="button" data-save="${i}">Suivre</button>
        <button class="small secondary" type="button" data-letter="${i}">Lettre de motivation</button>
      </div>
    </div>`;
}

function hostOf(url) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "";
  }
}

document.addEventListener("click", async (e) => {
  const save = e.target.dataset?.save;
  const letter = e.target.dataset?.letter;
  if (save !== undefined) {
    const o = offerStore[save];
    try {
      await api("/api/applications", {
        method: "POST",
        body: {
          title: o.title, company: o.company || "", contract_type: o.contract_type || "", location: o.location || "",
          url: o.url, offer_text: o.description || "",
        },
      });
      e.target.textContent = "Suivie ✓";
      e.target.disabled = true;
      toast("Ajoutée au suivi des candidatures.");
    } catch (err) {
      toast(err.message);
    }
  } else if (letter !== undefined) {
    const o = offerStore[letter];
    $("#letter-offer").value = [o.title, o.location, "", o.description || o.snippet || "", "", o.url].join("\n").trim();
    $("#letter-company").value = o.company || "";
    switchTab("letter");
    toast("Astuce : colle le texte complet de l'offre pour une lettre plus précise.");
  }
});

// ---------- Recherche d'offres ----------

$("#jobs-form").onsubmit = (e) => {
  e.preventDefault();
  const params = new URLSearchParams(new FormData(e.target));
  withBusy(e.submitter, async () => {
    const data = await api(`/api/jobs?${params}`);
    $("#jobs-links").innerHTML =
      "<span class='meta'>Rechercher aussi sur :</span>" +
      data.links.map((l) => `<a href="${escapeHtml(l.url)}" target="_blank" rel="noopener">${escapeHtml(l.name)} ↗</a>`).join("");

    let html = "";
    if (data.offers.length) {
      html += `<h2>France Travail (${data.offers.length})</h2>` + data.offers.map((o) => offerCard({ ...o, source: "France Travail" })).join("");
    } else if (data.error) {
      html += `<p class="meta">France Travail indisponible : ${escapeHtml(data.error)}</p>`;
    }
    if (data.web.length) {
      html += `<h2>Sur le web (${data.web.length})</h2>` + data.web.map((o) => offerCard({ ...o, source: "web" })).join("");
    } else if (data.web_error) {
      html += `<p class="meta">Recherche web indisponible : ${escapeHtml(data.web_error)}</p>`;
    }
    $("#jobs-results").innerHTML =
      html || "<p class='meta'>Aucune offre trouvée. Essaie d'autres mots-clés, ou demande à l'assistant de chercher pour toi.</p>";
  });
};

// ---------- CV & lettre ----------

$("#letter-btn").onclick = (e) =>
  withBusy(e.target, async () => {
    const { text } = await api("/api/letter", {
      method: "POST",
      body: { offer: $("#letter-offer").value, company: $("#letter-company").value, extra: $("#letter-extra").value },
    });
    showOutput($("#letter-output"), text);
  });

$("#cv-btn").onclick = (e) =>
  withBusy(e.target, async () => {
    const { text } = await api("/api/cv-review", { method: "POST", body: { offer: $("#letter-offer").value } });
    showOutput($("#letter-output"), text);
  });

// ---------- E-mails ----------

$("#email-btn").onclick = (e) =>
  withBusy(e.target, async () => {
    const { text } = await api("/api/email", {
      method: "POST",
      body: {
        received: $("#email-received").value,
        goal: $("#email-goal").value,
        tone: $("#email-tone").value,
        extra: $("#email-extra").value,
      },
    });
    showOutput($("#email-output"), text);
  });

// ---------- Suivi des candidatures ----------

let applications = [];

async function loadApplications() {
  try {
    applications = await api("/api/applications");
  } catch (err) {
    toast(err.message);
    return;
  }
  const select = $("#reply-form").elements.application_id;
  const chosen = select.value;
  select.innerHTML =
    '<option value="">Détecter automatiquement</option>' +
    applications
      .map((a) => `<option value="${a.id}">${escapeHtml(a.title)}${a.company ? " — " + escapeHtml(a.company) : ""}</option>`)
      .join("");
  select.value = chosen;

  const counts = {};
  applications.forEach((a) => (counts[a.status] = (counts[a.status] || 0) + 1));
  $("#tracker-summary").innerHTML =
    `<span>Total : ${applications.length}</span>` +
    Object.entries(STATUS_LABELS)
      .filter(([k]) => counts[k])
      .map(([k, label]) => `<span>${label} : ${counts[k]}</span>`)
      .join("");

  const today = new Date().toISOString().slice(0, 10);
  $("#tracker-list").innerHTML = applications.length
    ? applications
        .map((a) => {
          const late = a.next_action_on && a.next_action_on <= today && !["offre", "refuse"].includes(a.status);
          return `
      <div class="card" data-id="${a.id}">
        <h3>${escapeHtml(a.title)}${a.company ? " — " + escapeHtml(a.company) : ""}${a.prep ? '<span class="badge">Préparation prête</span>' : ""}</h3>
        <div class="meta">${escapeHtml([a.contract_type, a.location, a.contact].filter(Boolean).join(" · "))}</div>
        <div class="meta">
          ${a.applied_on ? "Postulé le " + escapeHtml(a.applied_on) : "Ajouté le " + escapeHtml(a.created_on)}
          ${a.next_action_on ? ` · <span class="${late ? "late" : ""}">Prochaine action : ${escapeHtml(a.next_action_on)}</span>` : ""}
        </div>
        ${a.notes ? `<div class="desc">${escapeHtml(a.notes)}</div>` : ""}
        <div class="actions">
          <select data-field="status">
            ${Object.entries(STATUS_LABELS)
              .map(([k, label]) => `<option value="${k}" ${k === a.status ? "selected" : ""}>${label}</option>`)
              .join("")}
          </select>
          ${a.url ? `<a href="${escapeHtml(a.url)}" target="_blank" rel="noopener"><button class="small secondary" type="button">Offre</button></a>` : ""}
          <button class="small" data-action="open">Fiche &amp; préparation</button>
          <button class="small secondary" data-action="followup">Rédiger une relance</button>
          <button class="small secondary" data-action="notes">Notes</button>
          <button class="small danger" data-action="delete">Supprimer</button>
        </div>
      </div>`;
        })
        .join("")
    : "<p class='meta'>Aucune candidature pour l'instant. Ajoute-en une ou suis une offre depuis l'onglet Offres.</p>";
}

$("#tracker-list").onchange = async (e) => {
  if (e.target.dataset.field !== "status") return;
  const id = e.target.closest(".card").dataset.id;
  const body = { status: e.target.value };
  const app = applications.find((a) => String(a.id) === id);
  if (body.status === "postule" && app && !app.applied_on) body.applied_on = new Date().toISOString().slice(0, 10);
  try {
    await api(`/api/applications/${id}`, { method: "PATCH", body });
    loadApplications();
  } catch (err) {
    toast(err.message);
  }
};

$("#tracker-list").onclick = async (e) => {
  const action = e.target.dataset.action;
  if (!action) return;
  const id = e.target.closest(".card").dataset.id;
  const app = applications.find((a) => String(a.id) === id);
  try {
    if (action === "delete") {
      if (!confirm("Supprimer cette candidature ?")) return;
      await api(`/api/applications/${id}`, { method: "DELETE" });
      loadApplications();
    } else if (action === "open") {
      openApplication(id);
    } else if (action === "notes") {
      const notes = prompt("Notes :", app.notes);
      if (notes === null) return;
      await api(`/api/applications/${id}`, { method: "PATCH", body: { notes } });
      loadApplications();
    } else if (action === "followup") {
      $("#email-received").value =
        `Candidature au poste « ${app.title} »${app.company ? " chez " + app.company : ""}` +
        `${app.applied_on ? ", envoyée le " + app.applied_on : ""}.` +
        `${app.contact ? "\nContact : " + app.contact : ""}${app.notes ? "\nNotes : " + app.notes : ""}`;
      $("#email-goal").value = "followup";
      switchTab("email");
    }
  } catch (err) {
    toast(err.message);
  }
};

$("#app-form").onsubmit = async (e) => {
  e.preventDefault();
  const body = Object.fromEntries(new FormData(e.target));
  body.status = body.applied_on ? "postule" : "a_postuler";
  try {
    await api("/api/applications", { method: "POST", body });
    e.target.reset();
    toast("Candidature ajoutée.");
    loadApplications();
  } catch (err) {
    toast(err.message);
  }
};

// ---------- Réponse d'un recruteur ----------

const REPLY_LABELS = {
  entretien: "Invitation à un entretien",
  test: "Test / étude de cas",
  offre: "Proposition d'embauche",
  refus: "Réponse négative",
  demande_infos: "Demande d'informations",
  autre: "Autre réponse",
};

$("#reply-form").onsubmit = (e) => {
  e.preventDefault();
  const form = e.target;
  const body = {
    message: form.elements.message.value,
    application_id: form.elements.application_id.value ? Number(form.elements.application_id.value) : null,
    offer_text: form.elements.offer_text.value,
  };
  withBusy(e.submitter, async () => {
    $("#reply-result").innerHTML = "<p class='meta'>Analyse du message, recherches sur l'entreprise et préparation en cours (jusqu'à une minute)…</p>";
    try {
      const { application: a, analysis, created, steps, prep_error } = await api("/api/recruiter-reply", { method: "POST", body });
      const when = [analysis.date_entretien, analysis.heure].filter(Boolean).join(" à ");
      $("#reply-result").innerHTML = `
        <div class="card">
          <h3>${escapeHtml(REPLY_LABELS[analysis.type_reponse] || "Réponse")} — ${escapeHtml(a.title)}${a.company ? " · " + escapeHtml(a.company) : ""}</h3>
          <div class="meta">Fiche ${created ? "créée" : "mise à jour"} · statut : ${escapeHtml(STATUS_LABELS[a.status] || a.status)}${when ? " · " + escapeHtml(when) : ""}${analysis.format ? " · " + escapeHtml(analysis.format) : ""}</div>
          ${analysis.resume ? `<div class="desc">${escapeHtml(analysis.resume)}</div>` : ""}
          ${analysis.a_faire ? `<div class="desc"><strong>À faire :</strong> ${escapeHtml(analysis.a_faire)}</div>` : ""}
          ${prep_error ? `<div class="desc late">Préparation non générée : ${escapeHtml(prep_error)} Tu pourras la relancer depuis la fiche.</div>` : ""}
          ${steps.length ? `<div class="steps">${steps.map((s) => `<div>🔎 ${escapeHtml(s)}</div>`).join("")}</div>` : ""}
          <div class="actions"><button class="small" type="button" data-action="open-reply" data-id="${a.id}">Ouvrir la fiche${a.prep ? " et la préparation" : ""}</button></div>
        </div>`;
      form.reset();
      loadApplications();
      if (a.prep) openApplication(a.id);
    } catch (err) {
      $("#reply-result").innerHTML = "";
      throw err;
    }
  });
};

$("#reply-result").onclick = (e) => {
  if (e.target.dataset.action === "open-reply") openApplication(e.target.dataset.id);
};

// ---------- Fiche détaillée d'une candidature ----------

let currentApp = null;

function renderApplication(a) {
  currentApp = a;
  $("#dlg-title").textContent = a.title + (a.company ? " — " + a.company : "");
  $("#dlg-meta").textContent = [
    STATUS_LABELS[a.status] || a.status,
    a.contract_type,
    a.location,
    a.contact,
    a.next_action_on && "Prochaine étape : " + a.next_action_on,
  ]
    .filter(Boolean)
    .join(" · ");
  $("#dlg-prepare").textContent = a.prep ? "Régénérer la préparation" : "Générer la préparation";
  $("#dlg-reply").hidden = !a.events?.length;
  $("#dlg-offer").value = a.offer_text || "";
  const prep = $("#dlg-prep");
  prep.innerHTML = "";
  if (a.prep) {
    const copy = document.createElement("button");
    copy.className = "secondary small copy-btn";
    copy.textContent = "Copier";
    copy.onclick = () => navigator.clipboard.writeText(a.prep).then(() => toast("Copié !"));
    const body = document.createElement("div");
    body.innerHTML = `<div class="meta">Préparation du ${escapeHtml(a.prep_updated_on)}</div>` + renderMarkdown(a.prep);
    prep.append(copy, body);
  }
  $("#dlg-events").innerHTML = a.events?.length
    ? a.events
        .map(
          (ev) => `
      <div class="card">
        <div class="meta">${escapeHtml(ev.date)} · ${escapeHtml(REPLY_LABELS[ev.kind.replace("reponse_", "")] || ev.kind)}</div>
        <div class="desc">${escapeHtml(ev.summary)}</div>
        <details><summary>Message complet</summary><div class="desc">${escapeHtml(ev.content)}</div></details>
      </div>`
        )
        .join("")
    : "<p class='meta'>Aucun échange enregistré. Colle les réponses du recruteur dans le bloc « J'ai reçu une réponse ».</p>";
}

async function openApplication(id) {
  try {
    renderApplication(await api(`/api/applications/${id}`));
    $("#dlg-steps").innerHTML = "";
    if (!$("#app-dialog").open) $("#app-dialog").showModal();
  } catch (err) {
    toast(err.message);
  }
}

$("#dlg-close").onclick = () => $("#app-dialog").close();

$("#dlg-prepare").onclick = (e) =>
  withBusy(e.target, async () => {
    $("#dlg-steps").innerHTML = "<div>Recherches sur l'entreprise et analyse des compétences en cours…</div>";
    try {
      const { application, steps } = await api(`/api/applications/${currentApp.id}/prepare`, { method: "POST" });
      renderApplication({ ...application, events: currentApp.events });
      $("#dlg-steps").innerHTML = steps.map((s) => `<div>🔎 ${escapeHtml(s)}</div>`).join("");
      loadApplications();
    } catch (err) {
      $("#dlg-steps").innerHTML = "";
      throw err;
    }
  });

$("#dlg-offer-save").onclick = async () => {
  try {
    const updated = await api(`/api/applications/${currentApp.id}`, { method: "PATCH", body: { offer_text: $("#dlg-offer").value } });
    currentApp = { ...updated, events: currentApp.events };
    toast("Fiche de poste enregistrée. Régénère la préparation pour en tenir compte.");
  } catch (err) {
    toast(err.message);
  }
};

$("#dlg-reply").onclick = () => {
  const last = currentApp.events[0];
  $("#email-received").value = last.content;
  $("#email-goal").value = ["reponse_entretien", "reponse_test", "reponse_offre"].includes(last.kind) ? "accept" : "reply";
  $("#app-dialog").close();
  switchTab("email");
};

// ---------- Profil ----------

api("/api/profile").then((p) => {
  const form = $("#profile-form");
  Object.entries(p).forEach(([k, v]) => form.elements[k] && (form.elements[k].value = v));
});

$("#profile-form").onsubmit = async (e) => {
  e.preventDefault();
  try {
    await api("/api/profile", { method: "PUT", body: Object.fromEntries(new FormData(e.target)) });
    toast("Profil enregistré.");
  } catch (err) {
    toast(err.message);
  }
};
