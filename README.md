# Helper — Job search center

Application web pour suivre ses candidatures (emploi, stage, alternance). Chaque utilisateur se connecte (Firebase Authentication) et ne voit que ses propres candidatures et fichiers. Interface en anglais ou en français (bouton EN / FR dans la barre latérale).

## Fonctionnalités

| Page | Ce que ça fait |
|---|---|
| **Box** | Liste des candidatures, triée par date du dernier changement de statut, filtrable par statut (Not sent, Sent, Positive response, Refused) et par recherche sur l'entreprise ou le poste. |
| **Candidature** | Page de lecture pensée pour répondre à un recruteur : points clés de l'offre d'abord (ou l'e-mail envoyé pour une candidature spontanée), puis l'offre, le CV, le contact, l'e-mail, la lettre. |
| **Création / modification** | Deux types : à une offre ou spontanée. Seules les bases sont obligatoires ; les sections (lien de l'offre, points clés, CV, lettre, e-mail, contact, section libre) s'ajoutent, se retirent et se réordonnent. **« Fetch and summarize »** lit la page de l'offre et l'IA (**Groq**) remplit les points clés ; un champ inconnu reste vide. |
| **Offer search** | Recherche d'offres sur le web et via l'API France Travail ; « Track » crée une candidature à partir d'une offre. |
| **Recruiter reply** | Colle le message d'un recruteur : l'IA en extrait le type de réponse (entretien, test, offre, demande d'infos, refus), la date, l'échéance et le contact. La candidature est retrouvée d'après l'entreprise et le poste (ou créée), puis mise à jour : statut, **prochaine étape** (affichée dans la Box), contact, historique des échanges. |
| **Préparation d'entretien** | Sur la page d'une candidature, générée automatiquement après une réponse positive : recherches web sur l'entreprise, puis fiche avec la situation, l'entreprise (sourcée), une **analyse détaillée de chaque compétence demandée** face au CV envoyé (ou à celui du profil), un pitch, les questions probables et à poser, une checklist. |
| **Assistant** | Discussion avec l'IA qui cherche elle-même sur le web : offres, entreprises qui recrutent, salaires, formations. |
| **Write** | Lettre de motivation (enregistrable dans la candidature), analyse de CV face à une offre, e-mails au recruteur (répondre, accepter, décliner, relancer, remercier), pré-remplis depuis une candidature. |
| **Profile** | Objectif, compétences et CV (import du texte depuis un PDF), utilisés par l'IA ; choix de partager ou non les statistiques d'usage. |
| **Statistics** | Réservée aux administrateurs (`ADMIN_UIDS`) : utilisateurs actifs par jour, entonnoir d'utilisation, usage et durée des fonctions IA, pages vues, dernières erreurs. |

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

### Essayer sans Firebase (mode démo)

Pour tester l'appli sur ton ordinateur sans configurer Firebase : seule `GROQ_API_KEY` est nécessaire dans `.env` (et `TAVILY_API_KEY`, conseillée, pour la recherche web).

```bash
python scripts/demo.py
```

Ouvre http://localhost:8000 : tu es connecté automatiquement avec un compte de démonstration, administrateur (page Statistics visible). Les données restent en mémoire et sont **effacées à l'arrêt** (Ctrl + C). Ce mode ne sert qu'aux essais locaux, jamais au déploiement.

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

### Recherche web : clé Tavily (recommandée, gratuite)

La recherche d'offres, l'assistant et la préparation d'entretien cherchent sur le web. Sans clé, l'appli utilise DuckDuckGo, qui **bloque souvent les requêtes automatiques** (« DuckDuckGo bloque les recherches… »). Pour une recherche fiable :

1. Crée un compte sur https://app.tavily.com (gratuit jusqu'à 1 000 recherches par mois, sans carte bancaire).
2. Copie la clé (elle commence par `tvly-`) dans `.env` : `TAVILY_API_KEY=...`, puis redémarre l'appli.

Si Tavily échoue (quota atteint…), DuckDuckGo prend le relais. En production : `printf %s "<clé>" | gcloud secrets create tavily-api-key --data-file=-`, puis ajoute `TAVILY_API_KEY=tavily-api-key:latest` à `--set-secrets`.

### API France Travail (optionnelle, gratuite)

Sans elle, Offer search cherche quand même sur le web. Crée une application sur https://francetravail.io, abonne-la à l'API **« Offres d'emploi v2 »** et copie ses identifiants dans `.env`.

### Statistiques d'usage (style PostHog)

À la première connexion, un bandeau demande l'accord de la personne ; sans accord, **rien n'est enregistré**. Avec accord, l'appli enregistre des événements (pages vues, candidature créée, offre résumée, réponse analysée, préparation générée, erreurs, durées des appels IA) dans la collection Firestore `events`, sans jamais de contenu (CV, offres, messages). Le choix se modifie dans Profile.

- **Page Statistics** : mets ton identifiant (affiché en bas de ta page Profile) dans `ADMIN_UIDS` (plusieurs identifiants séparés par des virgules).
- **PostHog (optionnel)** : crée un projet sur https://posthog.com (hébergement UE conseillé), puis renseigne `POSTHOG_API_KEY` (et `POSTHOG_HOST` si besoin). Les mêmes événements y sont envoyés par le serveur ; tu profites alors de ses tableaux de bord, entonnoirs et cohortes.

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

Pour France Travail, ajoute `FRANCE_TRAVAIL_CLIENT_ID` et `FRANCE_TRAVAIL_CLIENT_SECRET` de la même façon. Pour les statistiques, ajoute `ADMIN_UIDS=<ton uid>` à `--set-env-vars`, et la clé PostHog en secret si tu l'utilises (`--set-secrets POSTHOG_API_KEY=posthog-api-key:latest`).

## Tests

```bash
pytest
```

## Structure

```
app/
  main.py      # routes FastAPI (vérifie le jeton Firebase du cookie __session)
  store.py     # Firestore : candidatures, fichiers, profils, événements
  offer.py     # lecture d'une offre + résumé en points clés par l'IA
  replies.py   # réponses de recruteurs → mise à jour de la candidature ; préparation d'entretien
  agent.py     # assistant avec outils de recherche web (function calling)
  prompts.py   # prompts (assistant, lettre, CV, e-mails, réponses, préparation)
  analytics.py # statistiques d'usage : consentement, événements, PostHog, agrégats
  llm.py       # client Groq
  websearch.py # recherche web (DuckDuckGo) et lecture de pages
  jobs.py      # offres France Travail + liens externes
static/        # interface web sans build : app.js (Box, candidatures, offres), ai.js (pages IA),
               # stats.js (Statistics), track.js (envoi des événements), i18n.js (textes EN/FR), auth.js
tests/
```

## Confidentialité

Les candidatures et fichiers sont dans ton projet Firebase, rattachés au compte qui les a créés. Les textes (offre, message de recruteur, profil, CV) sont envoyés à Groq uniquement quand tu utilises une fonction IA. Les statistiques d'usage ne sont collectées qu'avec ton accord et ne contiennent aucun contenu.
