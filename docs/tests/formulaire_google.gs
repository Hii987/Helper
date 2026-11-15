/**
 * Crée le formulaire Google « Test de Helper » et la feuille de réponses associée.
 *
 * Utilisation :
 *   1. Ouvre https://script.google.com et clique sur « Nouveau projet ».
 *   2. Remplace tout le contenu par ce fichier, puis enregistre (Ctrl + S).
 *   3. Sélectionne la fonction « creerFormulaire » et clique sur « Exécuter ».
 *      Google demande l'autorisation de créer des formulaires et des feuilles dans ton Drive : accepte.
 *   4. Ouvre « Journal d'exécution » : il affiche le lien à envoyer aux testeurs
 *      et le lien pour modifier le formulaire.
 */

const NOTES = ["1", "2", "3", "4", "5"];
const CRITERES = ["Facile à comprendre et à utiliser", "Résultat utile pour moi", "Résultat fiable (pas d'erreur, pas d'invention)", "Rapidité"];
const TESTE = ["Oui, ça a marché", "Oui, mais j'ai eu un problème", "Non, je n'ai pas testé"];

function creerFormulaire() {
  const form = FormApp.create("Test de Helper — ton avis compte");
  form
    .setDescription(
      "Merci de tester Helper, un assistant gratuit pour chercher un emploi, un stage ou une alternance.\n\n" +
        "Durée : 20 à 30 minutes. Suis le guide du testeur que tu as reçu, puis réponds aux questions au fur et à mesure.\n" +
        "Notes : 1 = pas du tout satisfait, 5 = très satisfait.\n\n" +
        "Les réponses sont anonymes, sauf si tu choisis de laisser ton e-mail à la fin."
    )
    .setProgressBar(true)
    .setCollectEmail(false)
    .setAllowResponseEdits(true)
    .setConfirmationMessage("Merci beaucoup pour ton aide ! Tes retours vont directement servir à améliorer Helper.");

  // ---------- Profil du testeur ----------
  form.addPageBreakItem().setTitle("1. Qui es-tu ?");
  form.addTextItem().setTitle("Prénom ou pseudo (facultatif)");
  form.addMultipleChoiceItem()
    .setTitle("Ta situation actuelle")
    .setChoiceValues(["Lycéen·ne", "Étudiant·e", "Demandeur·se d'emploi", "En poste", "En reconversion"])
    .showOtherOption(true)
    .setRequired(true);
  form.addCheckboxItem()
    .setTitle("Que recherches-tu en ce moment ?")
    .setChoiceValues(["Un emploi (CDI, CDD…)", "Un stage", "Une alternance", "Rien pour l'instant"])
    .setRequired(true);
  form.addScaleItem()
    .setTitle("À l'aise avec l'informatique ?")
    .setBounds(1, 5)
    .setLabels("Pas du tout", "Très à l'aise")
    .setRequired(true);
  form.addCheckboxItem()
    .setTitle("Quels outils utilises-tu déjà pour ta recherche ?")
    .setChoiceValues([
      "Indeed", "LinkedIn", "Welcome to the Jungle", "France Travail", "HelloWork",
      "ChatGPT ou une autre IA", "Un tableur / carnet pour suivre mes candidatures", "Aucun",
    ])
    .showOtherOption(true);

  // ---------- Installation ----------
  form.addPageBreakItem()
    .setTitle("2. Installation")
    .setHelpText("Étapes 1 à 4 du guide : installer Python, récupérer Helper, ajouter la clé Groq et lancer l'application.");
  form.addMultipleChoiceItem()
    .setTitle("As-tu réussi à lancer Helper ?")
    .setChoiceValues(["Oui, seul·e", "Oui, avec de l'aide", "Non"])
    .setRequired(true);
  form.addMultipleChoiceItem()
    .setTitle("Sur quel ordinateur ?")
    .setChoiceValues(["Windows", "Mac", "Linux"])
    .showOtherOption(true);
  form.addMultipleChoiceItem()
    .setTitle("Combien de temps a pris l'installation ?")
    .setChoiceValues(["Moins de 10 min", "10 à 30 min", "Plus de 30 min", "Je n'ai pas réussi"]);
  form.addScaleItem().setTitle("L'installation était…").setBounds(1, 5).setLabels("Très difficile", "Très facile");
  form.addParagraphTextItem()
    .setTitle("Où as-tu bloqué ? Copie le message d'erreur si tu en as eu un.");

  // ---------- Fonctionnalités ----------
  ajouterFonctionnalite(form, "3. Profil",
    "Remplis l'onglet Profil (objectif, compétences, CV en texte) et clique sur Enregistrer.");
  ajouterFonctionnalite(form, "4. Assistant",
    "Onglet Assistant : demande par exemple « Trouve-moi des alternances en marketing à Lyon », " +
      "puis pose une question de suivi (« Lesquelles sont à moins de 30 min de Villeurbanne ? »).",
    ["Les offres proposées correspondaient-elles à ta demande ?"]);
  ajouterFonctionnalite(form, "5. Recherche d'offres",
    "Onglet Offres : lance une recherche avec tes propres mots-clés, ouvre une offre et clique sur « Suivre ».",
    ["Les offres trouvées étaient-elles pertinentes et récentes ?"]);
  ajouterFonctionnalite(form, "6. CV et lettre de motivation",
    "Onglet CV & lettre : colle une vraie annonce, génère la lettre de motivation, puis clique sur « Analyser / adapter mon CV ».",
    ["Enverrais-tu la lettre après quelques retouches ?"]);
  ajouterFonctionnalite(form, "7. E-mails",
    "Onglet E-mails : colle un mail de recruteur (ou utilise un exemple du guide) et génère une réponse.");

  // ---------- Nouveauté : réponses de recruteurs ----------
  form.addPageBreakItem()
    .setTitle("8. Réponse d'un recruteur et préparation d'entretien")
    .setHelpText(
      "C'est la fonctionnalité principale à tester. Onglet Candidatures → « J'ai reçu une réponse d'un recruteur » : " +
        "colle l'exemple A du guide (invitation à un entretien), clique sur « Analyser et préparer l'entretien », " +
        "puis lis la fiche de préparation. Recommence ensuite avec l'exemple B (refus)."
    );
  form.addMultipleChoiceItem().setTitle("As-tu testé cette fonctionnalité ?").setChoiceValues(TESTE).setRequired(true);
  form.addGridItem().setTitle("Ton évaluation").setRows(CRITERES).setColumns(NOTES);
  form.addCheckboxItem()
    .setTitle("Qu'est-ce qui a été bien fait automatiquement ?")
    .setChoiceValues([
      "Le type de réponse (entretien, refus…) a été bien reconnu",
      "La date et l'heure de l'entretien sont correctes",
      "La bonne candidature a été mise à jour (ou créée)",
      "Le contact du recruteur a été bien repris",
      "Le refus a bien fermé la candidature",
    ]);
  form.addGridItem()
    .setTitle("Qualité de la fiche de préparation")
    .setRows([
      "Présentation de l'entreprise",
      "Analyse des compétences demandées",
      "Mon niveau évalué pour chaque compétence",
      "Exemples à raconter (méthode STAR)",
      "Plan pour combler mes lacunes",
      "Questions probables du recruteur",
      "Questions à poser au recruteur",
      "Pitch d'une minute",
    ])
    .setColumns(NOTES);
  form.addMultipleChoiceItem()
    .setTitle("Utiliserais-tu cette fiche pour préparer un vrai entretien ?")
    .setChoiceValues(["Oui, telle quelle", "Oui, en la complétant", "Non"]);
  form.addParagraphTextItem().setTitle("Une information fausse, inventée ou inutile dans la fiche ?");
  form.addParagraphTextItem().setTitle("Que manque-t-il pour que tu sois vraiment prêt·e pour l'entretien ?");

  // ---------- Avis global ----------
  form.addPageBreakItem().setTitle("9. Ton avis global");
  form.addScaleItem()
    .setTitle("Recommanderais-tu Helper à un·e ami·e qui cherche un emploi, un stage ou une alternance ?")
    .setBounds(0, 10)
    .setLabels("Pas du tout", "Certainement")
    .setRequired(true);
  form.addMultipleChoiceItem()
    .setTitle("La fonctionnalité la plus utile pour toi")
    .setChoiceValues([
      "Assistant", "Recherche d'offres", "Lettre de motivation / CV", "E-mails",
      "Suivi des candidatures", "Réponse recruteur + préparation d'entretien",
    ]);
  form.addMultipleChoiceItem()
    .setTitle("La fonctionnalité la moins utile")
    .setChoiceValues([
      "Assistant", "Recherche d'offres", "Lettre de motivation / CV", "E-mails",
      "Suivi des candidatures", "Réponse recruteur + préparation d'entretien",
    ]);
  form.addCheckboxItem()
    .setTitle("Quelles nouveautés aimerais-tu voir ? (3 maximum)")
    .setChoiceValues([
      "Simulateur d'entretien : l'IA joue le recruteur et note mes réponses",
      "Tableau « à faire aujourd'hui » avec relances déjà rédigées",
      "Lecture automatique de ma boîte mail (Gmail, Outlook)",
      "Ajout des entretiens à mon agenda",
      "Bilan des compétences à travailler en priorité",
      "Compte rendu après entretien + mail de remerciement",
      "Statistiques sur mes candidatures",
      "Aide à la négociation du salaire",
      "Version en ligne, sans installation",
      "Application mobile",
    ])
    .showOtherOption(true)
    .setValidation(FormApp.createCheckboxValidation().requireSelectAtMost(3).build());
  form.addScaleItem()
    .setTitle("Es-tu à l'aise avec le fait que ton CV soit envoyé à une IA (Groq) lors des requêtes ?")
    .setBounds(1, 5)
    .setLabels("Pas du tout", "Totalement");
  form.addMultipleChoiceItem()
    .setTitle("Utiliserais-tu Helper pour ta vraie recherche ?")
    .setChoiceValues(["Oui", "Peut-être", "Non"])
    .setRequired(true);
  form.addParagraphTextItem().setTitle("Pourquoi ?");
  form.addParagraphTextItem().setTitle("Bugs rencontrés (ce que tu faisais, ce qui s'est passé, message d'erreur)");
  form.addParagraphTextItem().setTitle("Une dernière remarque ou idée ?");

  // ---------- Contact ----------
  form.addPageBreakItem().setTitle("10. Pour aller plus loin (facultatif)");
  form.addTextItem()
    .setTitle("Ton e-mail, si tu acceptes d'être recontacté·e pour un échange de 15 min ou une prochaine version")
    .setValidation(FormApp.createTextValidation().requireTextIsEmail().build());

  const sheet = SpreadsheetApp.create("Test de Helper — réponses");
  form.setDestination(FormApp.DestinationType.SPREADSHEET, sheet.getId());

  Logger.log("Lien à envoyer aux testeurs : " + form.getPublishedUrl());
  Logger.log("Lien pour modifier le formulaire : " + form.getEditUrl());
  Logger.log("Feuille des réponses : " + sheet.getUrl());
}

/** Une section par fonctionnalité : consigne, testé ?, grille de notes, questions spécifiques, commentaire. */
function ajouterFonctionnalite(form, titre, consigne, questionsOuiNon) {
  form.addPageBreakItem().setTitle(titre).setHelpText(consigne);
  form.addMultipleChoiceItem().setTitle("As-tu testé cette fonctionnalité ?").setChoiceValues(TESTE).setRequired(true);
  form.addGridItem().setTitle("Ton évaluation").setRows(CRITERES).setColumns(NOTES);
  (questionsOuiNon || []).forEach(function (q) {
    form.addMultipleChoiceItem().setTitle(q).setChoiceValues(["Oui", "En partie", "Non"]);
  });
  form.addParagraphTextItem().setTitle("Commentaires, problèmes ou idées");
}
