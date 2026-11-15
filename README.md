# Helper — Job search center

Application web locale pour suivre ses candidatures (emploi, stage, alternance). Interface en anglais ou en français (bouton EN / FR dans la barre latérale).

## Fonctionnalités

| Page | Ce que ça fait |
|---|---|
| **Box** | Liste des candidatures, triée par date du dernier changement de statut, filtrable par statut (Not sent, Sent, Positive response, Refused). |
| **Candidature** | Page de lecture pensée pour répondre à un recruteur : points clés de l'offre d'abord (ou l'e-mail envoyé pour une candidature spontanée), puis l'offre, le CV, le contact, l'e-mail, la lettre. |
| **Création / modification** | Deux types : à une offre ou spontanée. Seules les bases sont obligatoires ; les sections (lien de l'offre, points clés, CV, lettre, e-mail, contact, section libre) s'ajoutent, se retirent et se réordonnent. **« Fetch and summarize »** lit la page de l'offre et l'IA (**Groq**) remplit les points clés ; un champ inconnu reste vide. |
| **Offer search** | Recherche d'offres sur le web et via l'API France Travail ; « Track » crée une candidature à partir d'une offre. |

## Installation

Prérequis : Python 3.10+.

```bash
python -m venv .venv
source .venv/bin/activate        # Windows : .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # puis remplis les clés
uvicorn app.main:app --reload
```

Ouvre ensuite http://localhost:8000.

### Firestore (gratuit, plan Spark)

Les candidatures et les PDF sont stockés dans Firestore. Les PDF sont découpés en morceaux de 900 Ko (un document par morceau) : pas besoin de Cloud Storage, qui exige le plan payant.

1. Crée un projet dédié sur https://console.firebase.google.com (chaque projet a son propre quota gratuit) et mets son identifiant dans `.firebaserc`.
2. Crée la base et ses règles (seul le serveur y accède) : `firebase deploy --only firestore`.
3. *Paramètres du projet → Comptes de service → Générer une nouvelle clé privée* : garde le fichier JSON hors du dépôt.
4. Dans `.env` : `FIREBASE_PROJECT_ID=<id du projet>` et `GOOGLE_APPLICATION_CREDENTIALS=<chemin du JSON>`.

### Clé Groq (gratuite)

1. Crée une clé sur https://console.groq.com/keys.
2. Mets-la dans `.env` : `GROQ_API_KEY=...` (modèle modifiable via `GROQ_MODEL`).

### API France Travail (optionnelle, gratuite)

Sans elle, Offer search cherche quand même sur le web. Crée une application sur https://francetravail.io, abonne-la à l'API **« Offres d'emploi v2 »** et copie ses identifiants dans `.env`.

## Tests

```bash
pytest
```

## Structure

```
app/
  main.py      # routes FastAPI
  store.py     # Firestore : candidatures et fichiers
  offer.py     # lecture d'une offre + résumé en points clés par l'IA
  llm.py       # client Groq
  websearch.py # recherche web (DuckDuckGo) et lecture de pages
  jobs.py      # offres France Travail + liens externes
static/        # interface web (HTML/CSS/JS sans dépendance, textes dans i18n.js)
tests/
deprecated/    # ancien assistant, lettres, e-mails, préparation d'entretien (non branché, gardé pour réutilisation)
```

## Confidentialité

Les candidatures et fichiers sont dans ton projet Firebase. Le texte d'une offre est envoyé à Groq uniquement quand tu cliques sur « Fetch and summarize ».
