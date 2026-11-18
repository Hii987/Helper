# Helper — Job search center

Application web pour suivre ses candidatures (emploi, stage, alternance). Chaque utilisateur se connecte (Firebase Authentication) et ne voit que ses propres candidatures et fichiers. Interface en anglais ou en français (bouton EN / FR dans la barre latérale).

## Fonctionnalités

| Page | Ce que ça fait |
|---|---|
| **Box** | Liste des candidatures, triée par date du dernier changement de statut, filtrable par statut (Not sent, Sent, Positive response, Refused) et par recherche sur l'entreprise ou le poste. |
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
2. Crée la base, ses règles (seul le serveur y accède) et active la connexion par e-mail : `firebase deploy --only firestore,auth`.
3. *Paramètres du projet → Comptes de service → Générer une nouvelle clé privée* : garde le fichier JSON hors du dépôt.
4. Dans `.env` : `FIREBASE_PROJECT_ID=<id du projet>` et `GOOGLE_APPLICATION_CREDENTIALS=<chemin du JSON>`.

### Connexion (Firebase Authentication)

La configuration web du projet est dans `static/auth.js`. La connexion par e-mail est activée ; pour « Continue with Google », active le fournisseur Google dans la console : *Authentication → Sign-in method*.

### Clé Groq (gratuite)

1. Crée une clé sur https://console.groq.com/keys.
2. Mets-la dans `.env` : `GROQ_API_KEY=...` (modèle modifiable via `GROQ_MODEL`).

### API France Travail (optionnelle, gratuite)

Sans elle, Offer search cherche quand même sur le web. Crée une application sur https://francetravail.io, abonne-la à l'API **« Offres d'emploi v2 »** et copie ses identifiants dans `.env`.

## Déploiement (Cloud Run + Firebase Hosting)

Prérequis : plan **Blaze** (Cloud Run l'exige) ; pense à une alerte de budget. Le serveur tourne sur Cloud Run, Firebase Hosting le sert sur https://helper-job-search-center.web.app. Sur Cloud Run, pas de fichier de clé : le serveur accède à Firestore avec le compte de service par défaut.

```bash
gcloud auth login
gcloud config set project helper-job-search-center
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com

# Clé Groq en secret (une seule fois)
printf %s "<clé Groq>" | gcloud secrets create groq-api-key --data-file=-
gcloud secrets add-iam-policy-binding groq-api-key --role=roles/secretmanager.secretAccessor \
  --member=serviceAccount:263454823776-compute@developer.gserviceaccount.com

# À chaque mise à jour
gcloud run deploy job-search-center --source . --region europe-west1 --allow-unauthenticated \
  --set-env-vars FIREBASE_PROJECT_ID=helper-job-search-center --set-secrets GROQ_API_KEY=groq-api-key:latest
firebase deploy --only hosting
```

Pour France Travail, ajoute `FRANCE_TRAVAIL_CLIENT_ID` et `FRANCE_TRAVAIL_CLIENT_SECRET` de la même façon.

## Tests

```bash
pytest
```

## Structure

```
app/
  main.py      # routes FastAPI (vérifie le jeton Firebase du cookie __session)
  store.py     # Firestore : candidatures et fichiers
  offer.py     # lecture d'une offre + résumé en points clés par l'IA
  llm.py       # client Groq
  websearch.py # recherche web (DuckDuckGo) et lecture de pages
  jobs.py      # offres France Travail + liens externes
static/        # interface web (HTML/CSS/JS sans build, textes dans i18n.js, connexion dans auth.js)
tests/
deprecated/    # ancien assistant, lettres, e-mails, préparation d'entretien (non branché, gardé pour réutilisation)
```

## Confidentialité

Les candidatures et fichiers sont dans ton projet Firebase, rattachés au compte qui les a créés. Le texte d'une offre est envoyé à Groq uniquement quand tu cliques sur « Fetch and summarize ».
