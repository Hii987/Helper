# Helper — assistant emploi, stage & alternance

Application web locale qui t'aide à chercher un emploi, un stage ou une alternance, avec une IA gratuite (**Mistral AI**).

## Fonctionnalités

| Onglet | Ce que ça fait |
|---|---|
| **Assistant** | Discussion libre avec l'IA (orientation, conseils, préparation d'entretien…), personnalisée avec ton profil. |
| **Offres** | Recherche d'offres d'emploi / stage / alternance via l'API gratuite de France Travail, + liens directs vers Indeed, Welcome to the Jungle, LinkedIn, La bonne alternance, 1jeune1solution. Un clic pour suivre une offre ou générer la lettre de motivation. |
| **CV & lettre** | Génère une lettre de motivation adaptée à une offre, ou analyse ton CV (points forts, améliorations, mots-clés manquants). |
| **E-mails** | Rédige la réponse à un mail de recruteur : répondre, accepter un entretien, décliner, relancer, remercier — avec le ton choisi. |
| **Candidatures** | Suivi de tes candidatures (statut, dates, contact, notes), avec mise en évidence des relances en retard et bouton « Rédiger une relance ». |
| **Profil** | Ton objectif, tes compétences et ton CV, utilisés par l'IA. Stocké localement (SQLite). |

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

### Clé Mistral (gratuite)

1. Crée un compte sur https://console.mistral.ai
2. Choisis le plan gratuit **Experiment** et crée une clé dans *API Keys*.
3. Mets-la dans `.env` : `MISTRAL_API_KEY=...`

Le modèle par défaut est `mistral-small-latest` (modifiable via `MISTRAL_MODEL`). Le plan gratuit a des limites de débit : en cas de message « limite atteinte », attends quelques secondes.

### API France Travail (optionnelle, gratuite)

Sans elle, l'onglet Offres propose seulement des liens de recherche vers les sites d'offres.

1. Crée un compte sur https://francetravail.io et une application.
2. Abonne l'application à l'API **« Offres d'emploi v2 »**.
3. Copie l'identifiant et la clé secrète dans `.env` (`FRANCE_TRAVAIL_CLIENT_ID`, `FRANCE_TRAVAIL_CLIENT_SECRET`).

## Tests

```bash
pytest
```

## Structure

```
app/
  main.py     # routes FastAPI
  llm.py      # client Mistral
  prompts.py  # prompts (chat, lettre, CV, e-mails)
  jobs.py     # recherche d'offres France Travail + liens externes
  db.py       # SQLite : profil et candidatures
static/       # interface web (HTML/CSS/JS sans dépendance)
tests/
```

## Confidentialité

Les données (profil, candidatures) restent dans le fichier `helper.db` sur ta machine. Le contenu de ton profil et les textes que tu soumets sont envoyés à Mistral uniquement au moment d'une requête à l'IA.
