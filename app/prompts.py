"""Prompts système et construction des messages pour chaque outil."""

SYSTEM_BASE = (
    "Tu es Helper, un assistant bienveillant et concret qui aide une personne à trouver "
    "un métier, un stage, une alternance ou un emploi en France. Tu réponds en français, "
    "de façon claire et structurée, sans inventer d'informations sur la personne. "
    "Si une information manque, tu la signales ou tu poses une question."
)


def _profile_block(profile: dict) -> str:
    parts = []
    labels = {
        "name": "Nom",
        "target": "Objectif (métier, stage, alternance...)",
        "location": "Zone géographique",
        "skills": "Compétences",
        "cv": "CV / parcours",
    }
    for key, label in labels.items():
        value = (profile.get(key) or "").strip()
        if value:
            parts.append(f"{label} : {value}")
    if not parts:
        return "Aucun profil renseigné."
    return "Profil de la personne :\n" + "\n".join(parts)


def system_message(profile: dict) -> dict:
    return {"role": "system", "content": f"{SYSTEM_BASE}\n\n{_profile_block(profile)}"}


def chat_messages(profile: dict, history: list[dict]) -> list[dict]:
    # On ne garde que les rôles attendus et les 20 derniers échanges.
    clean = [
        {"role": m["role"], "content": m["content"]}
        for m in history
        if m.get("role") in ("user", "assistant") and m.get("content")
    ]
    return [system_message(profile)] + clean[-20:]


def cover_letter_messages(profile: dict, offer: str, company: str, extra: str) -> list[dict]:
    prompt = (
        "Rédige une lettre de motivation personnalisée (250 à 350 mots) pour l'offre ci-dessous. "
        "Appuie-toi uniquement sur le profil fourni ; mets entre [crochets] ce qui doit être complété. "
        "Structure : accroche, ce que j'apporte (liens concrets avec l'offre), pourquoi cette entreprise, "
        "conclusion avec demande d'entretien.\n\n"
        f"Entreprise : {company or 'non précisée'}\n"
        f"Consignes supplémentaires : {extra or 'aucune'}\n\n"
        f"Offre :\n{offer}"
    )
    return [system_message(profile), {"role": "user", "content": prompt}]


def cv_review_messages(profile: dict, offer: str) -> list[dict]:
    target = f"pour cette offre :\n{offer}" if offer.strip() else "de façon générale."
    prompt = (
        "Analyse mon CV et propose des améliorations concrètes " + target + "\n\n"
        "Réponds avec :\n"
        "1. Points forts\n"
        "2. Points à améliorer (avec exemples de reformulation)\n"
        "3. Mots-clés de l'offre absents du CV (si une offre est fournie)\n"
        "4. Une proposition de titre et d'accroche de CV"
    )
    return [system_message(profile), {"role": "user", "content": prompt}]


EMAIL_GOALS = {
    "reply": "répondre au mail reçu",
    "accept": "accepter la proposition (entretien, offre...) et confirmer les détails",
    "decline": "décliner poliment en laissant la porte ouverte",
    "followup": "relancer poliment suite à une candidature restée sans réponse",
    "thanks": "remercier après un entretien",
}


def email_messages(profile: dict, received: str, goal: str, tone: str, extra: str) -> list[dict]:
    goal_text = EMAIL_GOALS.get(goal, EMAIL_GOALS["reply"])
    prompt = (
        f"Rédige un e-mail professionnel pour {goal_text}. Ton : {tone or 'professionnel et chaleureux'}. "
        "Donne d'abord une ligne « Objet : ... », puis le corps du mail, court et clair, "
        "avec une formule de politesse adaptée. Mets entre [crochets] ce qui doit être complété.\n\n"
        f"Précisions : {extra or 'aucune'}\n\n"
        f"Mail reçu / contexte :\n{received or '(aucun mail reçu, il s’agit d’un premier envoi)'}"
    )
    return [system_message(profile), {"role": "user", "content": prompt}]
