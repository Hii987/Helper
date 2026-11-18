"""Statistiques d'usage « style PostHog » : événements, utilisateurs actifs, entonnoir, usage de l'IA.

- Les événements sont enregistrés dans Firestore (collection « events ») seulement pour les
  personnes qui ont accepté les statistiques (champ « analytics » du profil).
- Ils ne contiennent jamais de texte saisi (CV, offres, mails) : un nom d'événement et
  quelques propriétés courtes (page, statut, durée, nombre de résultats…).
- Si POSTHOG_API_KEY est défini, les mêmes événements sont aussi envoyés à PostHog
  (POSTHOG_HOST, par défaut l'hébergement européen).
"""

import os
import re
import threading
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

import httpx

from . import store

EVENT_NAME = re.compile(r"^\$?[a-z][a-z0-9_]{0,39}$")
MAX_PROPS = 20
MAX_BATCH = 50
CONSENT_TTL = 60  # secondes de cache du consentement

# Étapes de l'entrée dans l'appli jusqu'à la préparation d'entretien.
FUNNEL = (
    ("$pageview", "funnel.visit"),
    ("application_created", "funnel.created"),
    ("offer_summarized", "funnel.summarized"),
    ("reply_analyzed", "funnel.reply"),
    ("prep_generated", "funnel.prep"),
)
AI_EVENTS = ("offer_summarized", "reply_analyzed", "prep_generated", "chat_message", "text_written")

_consent: dict[str, tuple[bool, float]] = {}


def now() -> datetime:
    return datetime.now(timezone.utc)


def admin_uids() -> set[str]:
    return {u.strip() for u in os.getenv("ADMIN_UIDS", "").split(",") if u.strip()}


def consents(uid: str) -> bool:
    cached = _consent.get(uid)
    if cached and cached[1] > time.monotonic():
        return cached[0]
    allowed = store.get_profile(uid).get("analytics") == "yes"
    _consent[uid] = (allowed, time.monotonic() + CONSENT_TTL)
    return allowed


def forget_consent(uid: str) -> None:
    _consent.pop(uid, None)


def clean_props(props: dict | None) -> dict:
    """Garde des propriétés courtes et simples : jamais de texte libre long."""
    clean = {}
    for key, value in list((props or {}).items())[:MAX_PROPS]:
        if not isinstance(key, str) or not EVENT_NAME.match(key.lstrip("$") or "x"):
            continue
        if isinstance(value, bool) or isinstance(value, (int, float)):
            clean[key] = value
        elif isinstance(value, str):
            clean[key] = value[:120]
    return clean


def capture(uid: str, event: str, props: dict | None = None, session: str = "") -> None:
    capture_many(uid, [{"event": event, "props": props or {}}], session)


def capture_many(uid: str, events: list[dict], session: str = "") -> int:
    """Enregistre des événements ; renvoie le nombre gardé. Ne lève jamais d'erreur."""
    try:
        if not uid or not consents(uid):
            return 0
        stamp = now()
        rows = [{
            "uid": uid, "event": e["event"], "props": clean_props(e.get("props")),
            "session": str(session)[:64], "at": stamp.isoformat(timespec="milliseconds"),
        } for e in events[:MAX_BATCH] if isinstance(e.get("event"), str) and EVENT_NAME.match(e["event"])]
        if rows:
            store.add_events(rows)
            _forward_to_posthog(rows)
        return len(rows)
    except Exception:  # les statistiques ne doivent jamais casser l'appli
        return 0


def _forward_to_posthog(rows: list[dict]) -> None:
    key = os.getenv("POSTHOG_API_KEY")
    if not key:
        return
    host = os.getenv("POSTHOG_HOST", "https://eu.i.posthog.com").rstrip("/")
    batch = [{
        "event": r["event"], "distinct_id": r["uid"], "timestamp": r["at"],
        "properties": {**r["props"], "$session_id": r["session"] or None, "$lib": "helper-server"},
    } for r in rows]

    def send():
        try:
            httpx.post(f"{host}/batch/", json={"api_key": key, "batch": batch}, timeout=10)
        except httpx.HTTPError:
            pass

    threading.Thread(target=send, daemon=True).start()


# ---------- Tableau de bord ----------

def stats(days: int = 30) -> dict:
    """Agrège les événements des `days` derniers jours pour la page Statistiques."""
    days = max(1, min(days, 90))
    end = now()
    since = (end - timedelta(days=days)).isoformat(timespec="milliseconds")
    events = store.list_events(since)
    return summarize(events, days, end)


def summarize(events: list[dict], days: int, end: datetime) -> dict:
    day_keys = [(end - timedelta(days=i)).date().isoformat() for i in range(days - 1, -1, -1)]
    daily_users: dict[str, set] = defaultdict(set)
    daily_events: Counter = Counter()
    by_event: dict[str, dict] = defaultdict(lambda: {"count": 0, "users": set()})
    users_by_event: dict[str, set] = defaultdict(set)
    pages: Counter = Counter()
    ai = defaultdict(lambda: {"calls": 0, "errors": 0, "ms": []})
    errors, sessions, users = [], set(), set()

    for e in events:
        day, uid, name, props = e["at"][:10], e["uid"], e["event"], e.get("props") or {}
        users.add(uid)
        if e.get("session"):
            sessions.add(e["session"])
        daily_users[day].add(uid)
        daily_events[day] += 1
        by_event[name]["count"] += 1
        by_event[name]["users"].add(uid)
        if props.get("ok") is not False:  # un échec ne compte pas comme étape franchie
            users_by_event[name].add(uid)
        if name == "$pageview" and props.get("page"):
            pages[props["page"]] += 1
        if name in AI_EVENTS:
            ai[name]["calls"] += 1
            if props.get("ok") is False:
                ai[name]["errors"] += 1
            if isinstance(props.get("ms"), (int, float)):
                ai[name]["ms"].append(props["ms"])
        if props.get("ok") is False or name == "client_error":
            errors.append({"at": e["at"], "event": name, "error": props.get("error", "")})

    today = day_keys[-1]
    week = set(day_keys[-7:])
    funnel, reached = [], None
    for name, label in FUNNEL:
        step_users = users_by_event[name] if reached is None else reached & users_by_event[name]
        reached = step_users
        funnel.append({"event": name, "label": label, "users": len(step_users)})

    return {
        "days": days,
        "totals": {
            "users": len(users),
            "activeToday": len(daily_users.get(today, ())),
            "active7d": len(set().union(*(daily_users.get(d, set()) for d in week))),
            "events": len(events),
            "sessions": len(sessions),
        },
        "daily": [{"day": d, "users": len(daily_users.get(d, ())), "events": daily_events.get(d, 0)} for d in day_keys],
        "funnel": funnel,
        "features": sorted(
            ({"event": k, "count": v["count"], "users": len(v["users"])} for k, v in by_event.items()),
            key=lambda x: x["count"], reverse=True,
        ),
        "ai": [{
            "event": k, "calls": v["calls"], "errors": v["errors"],
            "avgMs": round(sum(v["ms"]) / len(v["ms"])) if v["ms"] else None,
        } for k, v in sorted(ai.items())],
        "pages": [{"page": p, "views": n} for p, n in pages.most_common(10)],
        "errors": sorted(errors, key=lambda x: x["at"], reverse=True)[:20],
    }
