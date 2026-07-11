"""
aziza/pipeline/fond.py
=======================
Évaluation du FOND (compréhension et fidélité) d'une contraction.

Pipeline :
  1. Embedding sémantique (Mistral Embed) → cosinus vs texte source
  2. LLM Few-Shot + CoT (Mistral Small) → note /3 + détection contresens
  3. Calibration hybride (sémantique + LLM)

Total Fond = /3
"""

import os
import re
import json
import time
import requests

# ── CONFIGURATION ────────────────────────────────────────────────────────────
MISTRAL_API_KEY = os.environ.get(
    "MISTRAL_API_KEY",
    "LR8lvqaaFuJ7TEWAVG4uR93vVdTotsvQ"
)
MODEL = "mistral-small-latest"
SMIN_SEM = 0.85

# ── PROMPT SYSTÈME AVEC CHAÎNE DE PENSÉE ────────────────────────────────────
SYSTEM_PROMPT = """Tu es un correcteur expert en Contraction de texte
pour le Baccalauréat béninois (séries A, B, C, D).

Tu reçois un TEXTE SOURCE et une CONTRACTION produite par un élève.

═══ CHAÎNE DE PENSÉE OBLIGATOIRE ═══
Avant de produire le JSON, raisonne intérieurement dans cet ordre :
1. IDENTIFIE les 3 à 5 idées directrices du texte source
2. VÉRIFIE chaque idée dans la contraction (présente / absente / déformée)
3. DÉTECTE les contresens (idée inversée ou trahie par rapport à l'auteur)
4. VÉRIFIE la neutralité : repère les pronoms personnels (je, moi, mon, mes)
   et expressions d'opinion (à mon avis, selon moi, personnellement,
   je pense, je crois, pour moi). Si présent → subjectivite_detectee: true
5. ATTRIBUE le score selon le barème ci-dessous
6. GÉNÈRE un feedback pédagogique ciblé sur l'erreur principale

═══ BARÈME score_fond /3 ═══
  3,0 → Toutes les idées essentielles présentes, aucun contresens, texte cohérent et fidèle.
  2,5 → Presque toutes les idées présentes, une omission mineure, pas de contresens.
  2,0 → 1–2 idées manquantes ou un contresens mineur, mais la thèse reste intacte.
  1,5 → Plusieurs omissions significatives, cohérence affaiblie.
  1,0 → Thèse principale absente ou gravement déformée.
  0,5 → Contresens majeur sur une idée secondaire, perte de sens notable.
  0,0 → Contresens majeur sur la thèse centrale (sens inversé ou totalement erroné).
  ATTENTION : la neutralité est une règle fondamentale de la contraction.
  En cas de subjectivité détectée, le score final sera pénalisé de -1pt
  (appliqué automatiquement après ta réponse).

═══ FORMAT DE SORTIE ═══
Réponds UNIQUEMENT avec un objet JSON valide, sans markdown, sans texte avant ou après :
{
  "score_fond": <0-3>,
  "contresens_detecte": <true|false>,
  "subjectivite_detectee": <true|false>,
  "phrase_subjective": "<citation exacte de la phrase subjective, vide si aucune>",
  "idees_manquantes": [<liste des idées absentes, vide si aucune>],
  "raisonnement": "<CoT : idées identifiées, vérification, décision de score — 2-3 phrases>",
  "feedback_erreur": "<diagnostic de l'erreur principale en 1 phrase>",
  "feedback_micro_cours": "<conseil pédagogique en 2-3 phrases>",
  "feedback_exemple": "<exemple concret de reformulation correcte en 1-2 phrases>"
}"""


FEW_SHOT_EXAMPLES = [
    {
        "role": "user",
        "content": (
            "TEXTE SOURCE (extrait) : 'La corruption est une pratique qui "
            "touche toutes les sphères de la société africaine, des "
            "administrations publiques aux entreprises privées.'\n\n"
            "CONTRACTION : 'La corruption en Afrique est limitée au "
            "secteur public et épargne complètement les entreprises privées.'"
        )
    },
    {
        "role": "assistant",
        "content": json.dumps({
            "score_fond": 0,
            "contresens_detecte": True,
            "idees_manquantes": ["La corruption touche aussi les entreprises privées"],
            "raisonnement": "Idée clé du texte : la corruption est universelle (secteurs public ET privé). Dans la contraction, l'élève écrit l'exact opposé. Contresens majeur. Score 0.",
            "feedback_erreur": "Contresens majeur : l'élève affirme que la corruption épargne les entreprises privées, alors que le texte source dit exactement le contraire.",
            "feedback_micro_cours": "Avant de rédiger, identifiez la thèse exacte de l'auteur. Ne transformez jamais une thèse inclusive en thèse restrictive.",
            "feedback_exemple": "Reformulation correcte : 'La corruption sévit dans toutes les couches de la société africaine, aussi bien dans les administrations publiques que dans les entreprises privées.'"
        }, ensure_ascii=False)
    },
    {
        "role": "user",
        "content": (
            "TEXTE SOURCE (extrait) : 'Les langues maternelles jouent un rôle "
            "déterminant dans la transmission des valeurs endogènes. Pourtant, "
            "les politiques linguistiques restent rarement suivies de mises en "
            "œuvre pratiques.'\n\n"
            "CONTRACTION : 'Les langues maternelles transmettent les valeurs "
            "culturelles propres à chaque peuple. Cependant, malgré des "
            "engagements officiels, les actions concrètes pour les promouvoir "
            "demeurent rares.'"
        )
    },
    {
        "role": "assistant",
        "content": json.dumps({
            "score_fond": 3,
            "contresens_detecte": False,
            "idees_manquantes": [],
            "raisonnement": "Deux idées clés présentes et fidèlement reformulées. Aucun contresens. Score 3.",
            "feedback_erreur": "Aucune erreur détectée.",
            "feedback_micro_cours": "Contraction exemplaire : les deux idées principales sont présentes et bien reformulées.",
            "feedback_exemple": "Voir le texte produit comme modèle de référence."
        }, ensure_ascii=False)
    },
    {
        "role": "user",
        "content": (
            "TEXTE SOURCE (extrait) : 'Le trafic d'enfants touche 53 pays africains. "
            "La pauvreté en est la cause principale mais non unique : "
            "la tradition et l'érosion des solidarités communautaires "
            "y contribuent également.'\n\n"
            "CONTRACTION : 'Le trafic d'enfants sévit dans 53 pays africains, "
            "alimenté principalement par la misère des populations rurales.'"
        )
    },
    {
        "role": "assistant",
        "content": json.dumps({
            "score_fond": 2,
            "contresens_detecte": False,
            "idees_manquantes": [
                "La tradition comme facteur contributif",
                "L'érosion des solidarités communautaires comme facteur contributif"
            ],
            "raisonnement": "Trois idées clés : (1) ampleur géographique, (2) pauvreté cause principale, (3) causes secondaires. L'élève omet (3). Pas de contresens, mais 2 idées manquantes. Score 2.",
            "feedback_erreur": "Omission des causes secondaires : tradition et érosion communautaire.",
            "feedback_micro_cours": "Une contraction doit restituer TOUTES les idées directrices.",
            "feedback_exemple": "Ajouter en fin : 'Mais la pauvreté n'est pas seule en cause : la tradition et la désintégration des solidarités communautaires y contribuent également.'"
        }, ensure_ascii=False)
    },
    {
        "role": "user",
        "content": (
            "TEXTE SOURCE (extrait) : 'La militarisation progressive des sociétés "
            "africaines, alimentée par des années de conflits armés, continue "
            "d'influencer négativement le déroulement des scrutins électoraux.'\n\n"
            "CONTRACTION : 'La militarisation croissante des sociétés africaines "
            "a paradoxalement renforcé la discipline électorale et amélioré la "
            "qualité des scrutins au fil des décennies.'"
        )
    },
    {
        "role": "assistant",
        "content": json.dumps({
            "score_fond": 2,
            "contresens_detecte": True,
            "idees_manquantes": [],
            "raisonnement": "Idée clé : la militarisation a un impact NÉGATIF sur les élections. L'élève reformule l'inverse. Contresens, mais thèse partiellement reconnue. Score 2.",
            "feedback_erreur": "Contresens sur l'effet de la militarisation.",
            "feedback_micro_cours": "Repérez les marqueurs de négativité comme 'influence négativement'.",
            "feedback_exemple": "Reformulation correcte : 'La militarisation héritée des conflits pèse négativement sur la qualité des scrutins.'"
        }, ensure_ascii=False)
    },
    {
        "role": "user",
        "content": (
            "TEXTE SOURCE (extrait) : 'Le travail des enfants reste un fléau "
            "dans les zones rurales où les familles démunies n'ont d'autre "
            "choix que de solliciter la force de travail de leurs enfants "
            "pour survivre.'\n\n"
            "CONTRACTION : 'Le travail des enfants est un problème grave dans "
            "les campagnes. Les familles pauvres sont obligées de faire "
            "travailler leurs enfants. À mon avis, c'est vraiment triste "
            "et le gouvernement devrait faire quelque chose.'"
        )
    },
    {
        "role": "assistant",
        "content": json.dumps({
            "score_fond": 2,
            "contresens_detecte": False,
            "subjectivite_detectee": True,
            "phrase_subjective": "À mon avis, c'est vraiment triste et le gouvernement devrait faire quelque chose.",
            "idees_manquantes": [],
            "raisonnement": "Deux idées clés présentes : (1) fléau en zones rurales, (2) pauvreté contraint les familles. Aucune idée manquante. MAIS l'élève ajoute une opinion personnelle avec 'À mon avis' et 'c'est vraiment triste', ce qui viole la règle de neutralité. Subjectivité détectée.",
            "feedback_erreur": "Violation de la neutralité : l'élève introduit son opinion personnelle avec 'À mon avis, c'est vraiment triste' alors que la contraction doit rester objective.",
            "feedback_micro_cours": "La contraction de texte interdit toute opinion personnelle. Vous devez uniquement reformuler les idées de l'auteur sans ajouter votre avis, vos sentiments ou vos suggestions.",
            "feedback_exemple": "Reformulation neutre : 'Le travail des enfants persiste dans les zones rurales où la pauvreté contraint les familles à employer leurs enfants pour survivre.'"
        }, ensure_ascii=False)
    },
]


# ── FONCTIONS AUXILIAIRES ────────────────────────────────────────────────────

def _clean_json_response(raw: str) -> dict:
    raw = re.sub(r'```json|```', '', raw).strip()
    raw = raw.replace('\u2019', "'").replace('\u2018', "'")
    raw = raw.replace('\u201c', '"').replace('\u201d', '"')
    raw = raw.replace('\u2013', '-').replace('\u2014', '-')

    match = re.search(r'\{.*\}', raw, re.DOTALL)
    if match:
        raw = match.group(0)

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    result = {}
    m = re.search(r'"score_fond"\s*:\s*(\d+(?:\.\d+)?)', raw)
    result['score_fond'] = float(m.group(1)) if m else 1.5
    result['score_fond'] = max(0, min(3, result['score_fond']))

    m = re.search(r'"contresens_detecte"\s*:\s*(true|false)', raw, re.IGNORECASE)
    result['contresens_detecte'] = (m.group(1).lower() == 'true') if m else False

    m = re.search(r'"subjectivite_detectee"\s*:\s*(true|false)', raw, re.IGNORECASE)
    result['subjectivite_detectee'] = (m.group(1).lower() == 'true') if m else False

    m = re.search(r'"phrase_subjective"\s*:\s*"(.*?)"(?=\s*[,}\]])', raw, re.DOTALL)
    result['phrase_subjective'] = m.group(1).strip() if m else ""

    m = re.search(r'"idees_manquantes"\s*:\s*\[([^\]]*)\]', raw, re.DOTALL)
    if m:
        content = m.group(1).strip()
        result['idees_manquantes'] = re.findall(r'"([^"]*)"', content) if content else []
    else:
        result['idees_manquantes'] = []

    for field in ['raisonnement', 'feedback_erreur', 'feedback_micro_cours', 'feedback_exemple']:
        pattern = rf'"{field}"\s*:\s*"(.*?)"(?=\s*[,}}\]])'
        m = re.search(pattern, raw, re.DOTALL)
        result[field] = m.group(1).strip() if m else ""
        if result[field]:
            result[field] = re.sub(r'\\n+', ' ', result[field]).strip()

    return result


def _mistral_embed(texte: str) -> list[float]:
    resp = requests.post(
        "https://api.mistral.ai/v1/embeddings",
        headers={"Authorization": f"Bearer {MISTRAL_API_KEY}"},
        json={"model": "mistral-embed", "input": texte},
        timeout=30
    )
    resp.raise_for_status()
    return resp.json()["data"][0]["embedding"]


def _call_llm(texte_source: str, contraction: str) -> dict:
    user_content = (
        f"TEXTE SOURCE :\n\"\"\"\n{texte_source[:1000]}\n\"\"\"\n\n"
        f"CONTRACTION DE L'ÉLÈVE :\n\"\"\"\n{contraction}\n\"\"\""
    )
    messages = FEW_SHOT_EXAMPLES + [{"role": "user", "content": user_content}]
    payload = {
        "model": MODEL,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + messages,
        "temperature": 0.2,
        "max_tokens": 800,
    }

    for attempt in range(1, 4):
        try:
            resp = requests.post(
                "https://api.mistral.ai/v1/chat/completions",
                headers={"Authorization": f"Bearer {MISTRAL_API_KEY}"},
                json=payload,
                timeout=60
            )
            resp.raise_for_status()
            data = resp.json()
            raw = data['choices'][0]['message']['content'].strip()
            result = _clean_json_response(raw)
            if 'score_fond' not in result:
                raise ValueError("score_fond manquant")
            return result
        except Exception as e:
            if attempt < 3:
                time.sleep(2)
            else:
                raise


def _calibrer(score_llm: float, contresens_llm: bool, score_sem: float,
              subjectivite: bool = False) -> tuple:
    if score_sem < 0.90 and score_llm >= 2.5:
        score_llm = max(1.0, score_llm - 0.5)
    if score_sem < 0.85 and not contresens_llm:
        contresens_llm = True
        score_llm = min(score_llm, 1.0)
    if subjectivite:
        score_llm = max(0.0, score_llm - 1.0)
    return score_llm, contresens_llm


# ── FONCTION PRINCIPALE ──────────────────────────────────────────────────────

def evaluer_fond(texte_source: str, contraction: str) -> dict:
    try:
        emb_src = _mistral_embed(texte_source)
        emb_ctr = _mistral_embed(contraction)
        dot = sum(a * b for a, b in zip(emb_src, emb_ctr))
        norm = (sum(a*a for a in emb_src) ** 0.5) * (sum(b*b for b in emb_ctr) ** 0.5)
        score_sem = dot / norm if norm > 0 else 0.0
    except Exception:
        score_sem = 0.0

    try:
        llm = _call_llm(texte_source, contraction)
        score_brut = llm["score_fond"]
        contresens = llm["contresens_detecte"]
        subjectivite = llm.get("subjectivite_detectee", False)
        phrase_subj = llm.get("phrase_subjective", "")
        idees_mq = llm.get("idees_manquantes", [])
        raisonnement = llm.get("raisonnement", "")
        feedback_err = llm.get("feedback_erreur", "")
        feedback_mc = llm.get("feedback_micro_cours", "")
        feedback_ex = llm.get("feedback_exemple", "")
    except Exception:
        score_brut = 1.5
        contresens = False
        subjectivite = False
        phrase_subj = ""
        idees_mq = []
        raisonnement = ""
        feedback_err = ""
        feedback_mc = ""
        feedback_ex = ""

    score_calibre, contresens_calibre = _calibrer(
        score_brut, contresens, score_sem, subjectivite
    )

    return {
        "score_fond_brut":       round(score_brut, 1),
        "score_fond_calibre":    round(score_calibre, 1),
        "contresens_detecte":    contresens_calibre,
        "subjectivite_detectee": subjectivite,
        "phrase_subjective":     phrase_subj,
        "idees_manquantes":      idees_mq,
        "score_semantique":      round(score_sem, 4),
        "raisonnement":          raisonnement,
        "feedback_erreur":       feedback_err,
        "feedback_micro_cours":  feedback_mc,
        "feedback_exemple":      feedback_ex,
    }
