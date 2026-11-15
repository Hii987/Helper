"""Stockage Firestore : candidatures et fichiers PDF.

Les PDF sont découpés en morceaux (un document par morceau) pour rester sous la limite
de 1 Mio par document Firestore, sans passer par Cloud Storage (payant).
"""

import os
from datetime import datetime, timezone
from functools import cache

from google.cloud import firestore

CHUNK_SIZE = 900_000


@cache
def _db() -> firestore.Client:
    return firestore.Client(project=os.getenv("FIREBASE_PROJECT_ID") or None)


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------- Candidatures ----------

def list_applications() -> list[dict]:
    return [{**d.to_dict(), "id": d.id} for d in _db().collection("applications").stream()]


def get_application(app_id: str) -> dict | None:
    doc = _db().collection("applications").document(app_id).get()
    return {**doc.to_dict(), "id": doc.id} if doc.exists else None


def create_application(data: dict) -> dict:
    ref = _db().collection("applications").document()
    ref.set(data)
    return {**data, "id": ref.id}


def update_application(app_id: str, data: dict) -> dict:
    _db().collection("applications").document(app_id).set(data)
    return {**data, "id": app_id}


def delete_application(app_id: str) -> None:
    _db().collection("applications").document(app_id).delete()


# ---------- Fichiers ----------

def save_file(meta: dict, content: bytes) -> str:
    ref = _db().collection("files").document()
    chunks = [content[i:i + CHUNK_SIZE] for i in range(0, len(content), CHUNK_SIZE)]
    ref.set({**meta, "chunks": len(chunks)})
    for i, chunk in enumerate(chunks):
        ref.collection("chunks").document(str(i)).set({"data": chunk})
    return ref.id


def get_file(file_id: str) -> tuple[dict, bytes] | None:
    ref = _db().collection("files").document(file_id)
    doc = ref.get()
    if not doc.exists:
        return None
    meta = doc.to_dict()
    content = b"".join(ref.collection("chunks").document(str(i)).get().get("data") for i in range(meta["chunks"]))
    return meta, content


def get_file_meta(file_id: str) -> dict | None:
    doc = _db().collection("files").document(file_id).get()
    return doc.to_dict() if doc.exists else None


def delete_file(file_id: str) -> None:
    ref = _db().collection("files").document(file_id)
    for chunk in ref.collection("chunks").stream():
        chunk.reference.delete()
    ref.delete()
