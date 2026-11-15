"""Stockage SQLite : profil unique + suivi des candidatures et de leurs échanges."""

import os
import sqlite3
from contextlib import contextmanager
from datetime import date

PROFILE_FIELDS = ("name", "target", "location", "skills", "cv")
APPLICATION_FIELDS = (
    "title", "company", "contract_type", "location", "url",
    "status", "applied_on", "next_action_on", "contact", "notes",
    "offer_text", "prep", "prep_updated_on",
)
STATUSES = ("a_postuler", "postule", "relance", "entretien", "offre", "refuse")


def db_path() -> str:
    return os.getenv("HELPER_DB_PATH", "helper.db")


@contextmanager
def connect():
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS profile ("
            "id INTEGER PRIMARY KEY CHECK (id = 1), "
            + ", ".join(f"{f} TEXT DEFAULT ''" for f in PROFILE_FIELDS)
            + ")"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS applications ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            + ", ".join(f"{f} TEXT DEFAULT ''" for f in APPLICATION_FIELDS)
            + ", created_on TEXT)"
        )
        # Bases créées avant l'ajout de colonnes : on complète le schéma.
        existing = {r["name"] for r in conn.execute("PRAGMA table_info(applications)")}
        for field in APPLICATION_FIELDS:
            if field not in existing:
                conn.execute(f"ALTER TABLE applications ADD COLUMN {field} TEXT DEFAULT ''")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS events ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "application_id INTEGER NOT NULL, "
            "date TEXT, kind TEXT, summary TEXT DEFAULT '', content TEXT DEFAULT '')"
        )


def get_profile() -> dict:
    with connect() as conn:
        row = conn.execute("SELECT * FROM profile WHERE id = 1").fetchone()
    if row is None:
        return {f: "" for f in PROFILE_FIELDS}
    return {f: row[f] or "" for f in PROFILE_FIELDS}


def save_profile(data: dict) -> dict:
    values = [data.get(f, "") or "" for f in PROFILE_FIELDS]
    with connect() as conn:
        conn.execute(
            f"INSERT INTO profile (id, {', '.join(PROFILE_FIELDS)}) "
            f"VALUES (1, {', '.join('?' for _ in PROFILE_FIELDS)}) "
            "ON CONFLICT(id) DO UPDATE SET "
            + ", ".join(f"{f} = excluded.{f}" for f in PROFILE_FIELDS),
            values,
        )
    return get_profile()


def list_applications() -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM applications ORDER BY id DESC").fetchall()
    return [dict(r) for r in rows]


def get_application(app_id: int) -> dict | None:
    with connect() as conn:
        row = conn.execute("SELECT * FROM applications WHERE id = ?", (app_id,)).fetchone()
    return dict(row) if row else None


def create_application(data: dict) -> dict:
    values = {f: data.get(f, "") or "" for f in APPLICATION_FIELDS}
    if values["status"] not in STATUSES:
        values["status"] = "a_postuler"
    with connect() as conn:
        cur = conn.execute(
            f"INSERT INTO applications ({', '.join(APPLICATION_FIELDS)}, created_on) "
            f"VALUES ({', '.join('?' for _ in APPLICATION_FIELDS)}, ?)",
            [*values.values(), date.today().isoformat()],
        )
        app_id = cur.lastrowid
    return get_application(app_id)


def update_application(app_id: int, data: dict) -> dict | None:
    fields = {f: data[f] or "" for f in APPLICATION_FIELDS if f in data}
    if "status" in fields and fields["status"] not in STATUSES:
        raise ValueError(f"Statut inconnu : {fields['status']}")
    if fields:
        with connect() as conn:
            conn.execute(
                f"UPDATE applications SET {', '.join(f'{f} = ?' for f in fields)} WHERE id = ?",
                [*fields.values(), app_id],
            )
    return get_application(app_id)


def delete_application(app_id: int) -> bool:
    with connect() as conn:
        conn.execute("DELETE FROM events WHERE application_id = ?", (app_id,))
        cur = conn.execute("DELETE FROM applications WHERE id = ?", (app_id,))
    return cur.rowcount > 0


def add_event(app_id: int, kind: str, summary: str = "", content: str = "") -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO events (application_id, date, kind, summary, content) VALUES (?, ?, ?, ?, ?)",
            (app_id, date.today().isoformat(), kind, summary, content),
        )


def list_events(app_id: int) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM events WHERE application_id = ? ORDER BY id DESC", (app_id,)
        ).fetchall()
    return [dict(r) for r in rows]
