"""Mode démo local : l'appli complète sans Firebase, pour l'essayer sur son ordinateur.

- Connexion automatique avec un compte de démonstration (pas de Firebase Authentication).
- Candidatures, fichiers, profil et statistiques gardés en mémoire : tout est effacé à l'arrêt.
- Vraie IA Groq : il faut GROQ_API_KEY dans le fichier .env.
- Le compte de démo est administrateur : la page Statistiques est visible.

Lancement, depuis le dossier du projet :  python scripts/demo.py
puis ouvrir http://localhost:8000. Ne jamais utiliser ce mode pour un déploiement.
"""

import os
import sys
from pathlib import Path

import uvicorn
from fastapi.responses import Response
from starlette.routing import Route

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DEMO_UID = "demo-user"
os.environ["ADMIN_UIDS"] = DEMO_UID

from app import main, store  # noqa: E402

# Remplace la connexion Firebase de l'interface par une connexion automatique.
AUTH_STUB = """window.authApi = { signIn: async () => {}, signUp: async () => {}, google: async () => {},
  signOut: async () => alert("Mode démo : la déconnexion est désactivée.") };
setTimeout(() => onAuth({ uid: "%s" }), 0);""" % DEMO_UID


def auth_stub(_request):
    return Response(AUTH_STUB, media_type="application/javascript")


def use_memory_store() -> None:
    """Remplace Firestore par des dictionnaires en mémoire."""
    apps, files, profiles, events = {}, {}, {}, []

    def create_application(data):
        app_id = f"demo{len(apps) + 1}"
        apps[app_id] = data
        return {**data, "id": app_id}

    def save_file(meta, content):
        file_id = f"file{len(files) + 1}"
        files[file_id] = (meta, content)
        return file_id

    def save_profile(uid, data):
        profiles.setdefault(uid, {}).update(data)
        return dict(profiles[uid])

    replacements = {
        "list_applications": lambda uid: [{**d, "id": k} for k, d in apps.items() if d.get("uid") == uid],
        "get_application": lambda k: {**apps[k], "id": k} if k in apps else None,
        "create_application": create_application,
        "update_application": lambda k, d: apps.__setitem__(k, d) or {**d, "id": k},
        "delete_application": lambda k: apps.pop(k, None),
        "save_file": save_file,
        "get_file": lambda k: files.get(k),
        "get_file_meta": lambda k: files[k][0] if k in files else None,
        "delete_file": lambda k: files.pop(k, None),
        "get_profile": lambda uid: dict(profiles.get(uid, {})),
        "save_profile": save_profile,
        "add_events": events.extend,
        "list_events": lambda since, limit=20000: [e for e in events if e["at"] >= since][-limit:],
    }
    for name, fn in replacements.items():
        setattr(store, name, fn)


if __name__ == "__main__":
    if os.getenv("K_SERVICE"):  # variable définie par Cloud Run
        sys.exit("Le mode démo ne doit pas tourner en production.")
    use_memory_store()
    main.app.dependency_overrides[main.current_user] = lambda: DEMO_UID
    main.app.router.routes.insert(0, Route("/static/auth.js", auth_stub))
    if not os.getenv("GROQ_API_KEY"):
        print("Attention : GROQ_API_KEY manque dans .env, les fonctions IA ne marcheront pas.")
    print("Mode démo : ouvre http://localhost:8000 (Ctrl + C pour arrêter, les données sont alors effacées).")
    uvicorn.run(main.app, host="127.0.0.1", port=int(os.getenv("PORT", "8000")), log_level="warning")
