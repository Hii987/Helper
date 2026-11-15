# Guide du testeur — Helper

Merci de tester **Helper**, un assistant gratuit pour chercher un emploi, un stage ou une alternance.
Compte **20 à 30 minutes**. Garde le formulaire d'avis ouvert à côté et réponds au fur et à mesure.

> Lien du formulaire : **[à compléter]**

## 1. Installer Python (5 min, une seule fois)

Télécharge Python 3.10 ou plus récent sur https://www.python.org/downloads/.
Sous Windows, coche **« Add Python to PATH »** au début de l'installation.

## 2. Récupérer Helper

- **Sans Git** : télécharge https://github.com/Hii987/Helper/archive/refs/heads/main.zip, puis décompresse le dossier.
- **Avec Git** : `git clone https://github.com/Hii987/Helper.git`

Ouvre ensuite un terminal **dans le dossier Helper** :
- Windows : ouvre le dossier, tape `cmd` dans la barre d'adresse, puis appuie sur Entrée.
- Mac : clic droit sur le dossier → *Nouveau terminal au dossier*.

Puis tape :

```
python -m venv .venv
```

| Windows | Mac / Linux |
|---|---|
| `.venv\Scripts\activate` | `source .venv/bin/activate` |

```
pip install -r requirements.txt
```

(Sur Mac, si `python` n'est pas reconnu, utilise `python3`.)

## 3. Ajouter ta clé d'IA gratuite (3 min)

1. Crée un compte sur https://console.groq.com, puis une clé dans **API Keys**.
2. Dans le dossier Helper, copie le fichier `.env.example` et renomme la copie en `.env`.
3. Ouvre `.env` avec le Bloc-notes et colle ta clé après le `=`, sans espace ni guillemets :
   `GROQ_API_KEY=gsk_...`

## 4. Lancer Helper

```
uvicorn app.main:app
```

Ouvre **http://localhost:8000** dans ton navigateur. En haut, « IA Groq connectée » doit apparaître en vert.
Pour arrêter : **Ctrl + C** dans le terminal.

👉 Réponds à la section **« Installation »** du formulaire, même (surtout !) si tu as bloqué.

## 5. Les scénarios à tester

Utilise ta vraie situation quand c'est possible, c'est ce qui rend tes retours précieux.

1. **Profil** : remplis l'onglet *Profil* (objectif, compétences, CV copié-collé en texte) et enregistre.
2. **Assistant** : demande « Trouve-moi des [stages / alternances / emplois] en [métier] à [ville] », puis pose une question de suivi.
3. **Offres** : fais une recherche, ouvre une offre, clique sur **Suivre**.
4. **CV & lettre** : colle une vraie annonce (ou l'exemple C ci-dessous), génère la lettre, puis l'analyse de CV.
5. **E-mails** : colle l'exemple A et génère une réponse « Accepter ».
6. **Réponse d'un recruteur** ⭐ (le plus important) :
   - Onglet *Candidatures* → *J'ai reçu une réponse d'un recruteur*.
   - Colle l'**exemple A**, colle l'**exemple C** dans « Fiche de poste », puis clique sur **Analyser et préparer l'entretien**.
   - Lis la fiche de préparation en entier : est-elle juste ? utile ? te sentirais-tu prêt·e ?
   - Colle ensuite l'**exemple B** : la candidature doit passer en « Refusé ».

## Exemples à copier-coller

### Exemple A — invitation à un entretien

```
Objet : Votre candidature – Assistant(e) marketing digital en alternance

Bonjour,

Nous avons bien reçu votre candidature pour le poste d'assistant(e) marketing digital en alternance
chez Decathlon et elle a retenu toute notre attention.

Nous vous proposons un premier entretien en visio avec Claire Dubois, responsable marketing, et
moi-même mardi prochain à 10h30 (durée : 45 minutes). Le lien Teams vous sera envoyé après confirmation.

Merci de me confirmer votre disponibilité et de m'envoyer votre calendrier d'alternance.

Bien cordialement,
Thomas Leroy
Chargé de recrutement – thomas.leroy@exemple.fr
```

### Exemple B — refus

```
Bonjour,

Nous vous remercions de l'intérêt que vous portez à Decathlon. Après étude attentive de votre
candidature au poste d'assistant(e) marketing digital en alternance, nous sommes au regret de vous
informer qu'elle n'a pas été retenue.

Nous vous souhaitons une pleine réussite dans vos recherches.

Thomas Leroy
```

### Exemple C — fiche de poste

```
Assistant(e) marketing digital – Alternance 12 à 24 mois – Villeneuve-d'Ascq

Missions :
- Participer à la création et au suivi des campagnes sur les réseaux sociaux (Instagram, TikTok, LinkedIn)
- Rédiger des contenus web optimisés pour le SEO
- Suivre les indicateurs de performance (Google Analytics, Meta Business Suite) et produire un reporting mensuel
- Contribuer à l'organisation d'événements en magasin

Profil :
- Formation Bac+3 à Bac+5 en marketing / communication
- Maîtrise du pack Office, notions de Canva ou de la suite Adobe
- Anglais professionnel
- Curieux(se), organisé(e), à l'aise à l'écrit, passionné(e) de sport
```

## Signaler un bug

Dans le formulaire, indique : ce que tu faisais, ce qui s'est passé, et le message d'erreur.
Une capture d'écran du terminal est aussi bienvenue.

**Confidentialité** : tes données restent sur ton ordinateur (fichier `helper.db`). Seuls les textes
envoyés à l'IA au moment d'une requête (profil, CV, messages) passent par Groq.
Tu peux utiliser un CV anonymisé si tu préfères.

Merci 🙏
