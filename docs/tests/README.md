# Campagne de tests utilisateurs

| Fichier | Rôle |
|---|---|
| `formulaire_google.gs` | Script qui crée automatiquement le formulaire Google et sa feuille de réponses |
| `guide_testeurs.md` | Guide à envoyer aux testeurs : installation, scénarios, exemples à copier-coller |

## Créer le formulaire (5 min)

1. Va sur https://script.google.com → **Nouveau projet**.
2. Efface le contenu, colle tout `formulaire_google.gs`, puis enregistre.
3. En haut, choisis la fonction `creerFormulaire` et clique sur **Exécuter**. Accepte les autorisations
   (Google affiche « application non validée » : *Paramètres avancés → Accéder au projet*, car c'est ton propre script).
4. Dans le **Journal d'exécution**, récupère les 3 liens : formulaire à envoyer, édition, feuille des réponses.
5. Colle le lien du formulaire en haut de `guide_testeurs.md` (ligne « Lien du formulaire »).

Le formulaire est ensuite modifiable normalement dans Google Forms. Pense à vérifier l'aperçu (icône 👁).

## Message à envoyer aux testeurs

> Salut ! Je développe **Helper**, un assistant gratuit pour chercher un emploi, un stage ou une alternance
> (recherche d'offres, lettres de motivation, suivi des candidatures, préparation d'entretien).
> J'ai besoin de ton avis : ça prend 20 à 30 minutes.
>
> 1. Suis le guide pour l'installer : [lien vers guide_testeurs.md]
> 2. Teste les scénarios et réponds au formulaire : [lien du formulaire]
>
> Tes retours sont anonymes. Merci beaucoup !

Le lien GitHub du guide est : https://github.com/Hii987/Helper/blob/main/docs/tests/guide_testeurs.md

## Conseils

- **Testeurs variés** : 5 à 8 personnes suffisent pour trouver la plupart des problèmes. Mélange profils
  (lycéen, étudiant, demandeur d'emploi, reconversion) et aisance avec l'informatique.
- **Observe 1 ou 2 personnes en direct**, en visio avec partage d'écran, sans les aider : c'est là qu'on voit les vrais blocages,
  surtout à l'installation.
- **Clé Groq** : chaque testeur crée la sienne (gratuite). Évite de partager la tienne : son quota gratuit serait vite épuisé.
- **Analyse** : dans la feuille des réponses, regarde en priorité le taux de réussite de l'installation,
  le score de recommandation (note de 9-10 = promoteur, 0-6 = détracteur) et les nouveautés les plus demandées.
