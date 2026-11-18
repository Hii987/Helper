// Statistiques d'usage : pages vues et erreurs, envoyées par lots au serveur.
// Le serveur ignore tout tant que la personne n'a pas accepté (profil > statistiques),
// et ne garde jamais de texte saisi : seulement le nom de la page ou de l'erreur.

const tracker = {
  queue: [],
  session: (() => {
    try {
      let id = sessionStorage.getItem("session");
      if (!id) sessionStorage.setItem("session", (id = Math.random().toString(36).slice(2) + Date.now().toString(36)));
      return id;
    } catch {
      return Math.random().toString(36).slice(2);
    }
  })(),
  enabled: false, // vrai une fois le consentement connu et accepté
};

function track(event, props = {}) {
  if (!tracker.enabled) return;
  tracker.queue.push({ event, props: { ...props, lang, screen: innerWidth < 600 ? "mobile" : "desktop" } });
  if (tracker.queue.length >= 20) flushEvents();
}

function flushEvents() {
  if (!tracker.queue.length) return;
  const events = tracker.queue.splice(0);
  // keepalive : l'envoi aboutit même si la page se ferme.
  fetch("/api/events", {
    method: "POST", keepalive: true, headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ events, session: tracker.session }),
  }).catch(() => {});
}

setInterval(flushEvents, 10000);
addEventListener("pagehide", flushEvents);
addEventListener("visibilitychange", () => document.visibilityState === "hidden" && flushEvents());
addEventListener("error", (e) => track("client_error", { error: String(e.message).slice(0, 100), ok: false }));

// Nom de page sans identifiant : « #/a/abc123/edit » devient « application_edit ».
function pageName(hash) {
  const [, page = "", id, sub] = hash.split("/");
  if (page === "a") return sub ? `application_${sub}` : "application";
  if (page === "write") return id ? `write_${id}` : "write";
  return page || "box";
}
