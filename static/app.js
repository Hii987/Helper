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
        body: { title: o.title, company: o.company || "", contract_type: o.contract_type || "", location: o.location || "", url: o.url },
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
        <h3>${escapeHtml(a.title)}${a.company ? " — " + escapeHtml(a.company) : ""}</h3>
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
