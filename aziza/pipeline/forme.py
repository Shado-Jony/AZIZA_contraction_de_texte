"""
aziza/pipeline/forme.py
========================
Évaluation de la FORME (aspects linguistiques) d'une contraction.

Composantes :
  - Lexical (/3)   : LCS normalisé (score parabolique) + pénalité quota
  - Syntaxe (/2)   : ratio phrases + connecteurs logiques
  - Orthographe (/2) : LanguageTool (API distante)

Total Forme = /7
"""

import re
import os
from .similarite import lcs_score, SMIN, label_plagiat

# ── CONNECTEURS LOGIQUES ─────────────────────────────────────────────────────
CONNECTEURS = {
    'addition': [
        'de plus', 'en outre', 'par ailleurs', 'aussi', 'également', 'de surcroît',
        'de même', 'sans compter que', 'encore', 'outre cela'
    ],
    'opposition': [
        'cependant', 'néanmoins', 'toutefois', 'en revanche', 'par contre', 'pourtant',
        'au contraire', 'malgré tout', 'or', 'quand même'
    ],
    'consequence': [
        'donc', 'ainsi', 'par conséquent', 'c\'est pourquoi', 'en conséquence', 'dès lors',
        'de sorte que', 'si bien que', 'alors', 'par suite'
    ],
    'illustration': [
        'par exemple', 'notamment', 'en l\'occurrence', 'à savoir', 'tel que',
        'entre autres', 'c\'est le cas de'
    ],
    'organisation': [
        'premièrement', 'deuxièmement', 'ensuite', 'en premier lieu', 'd\'une part',
        'd\'autre part', 'd\'abord', 'enfin', 'pour conclure', 'en somme', 'en résumé',
        'pour commencer', 'pour terminer', 'en définitive'
    ],
    'cause': [
        'car', 'parce que', 'puisque', 'étant donné que', 'vu que', 'en raison de',
        'du fait que'
    ],
    'but': [
        'afin que', 'pour que', 'dans le but de', 'en vue de', 'de manière à',
        'de façon à', 'dans l\'intention de'
    ],
    'condition': [
        'si', 'à condition que', 'pourvu que', 'dans la mesure où', 'en cas de',
        'à supposer que', 'à moins que'
    ],
    'temps': [
        'quand', 'lorsque', 'au moment où', 'pendant que', 'tandis que',
        'dès que', 'aussitôt que', 'avant que', 'après que'
    ]
}


# ── FONCTIONS AUXILIAIRES ────────────────────────────────────────────────────

def compter_phrases(texte: str) -> int:
    return max(1, len(re.split(r'[.!?]+', texte)) - 1)


def analyser_connecteurs(texte: str) -> dict:
    texte_lower = texte.lower()
    total = 0
    categories = 0
    details = {}
    for cat, mots in CONNECTEURS.items():
        count = sum(1 for m in mots if m in texte_lower)
        details[cat] = count
        total += count
        if count > 0:
            categories += 1
    return {"conn_total": total, "conn_categories": categories, "conn_details": details}


def penalite_quota(ecart_pct: float) -> float:
    return min(2.0, ecart_pct / 50)


def score_plagiat_parabole(lcs: float) -> float:
    SMAX = 0.80
    if lcs < SMIN or lcs >= SMAX:
        return 0.0
    M = (SMIN + SMAX) / 2
    H = (SMAX - SMIN) / 2
    score = -1.50 / (H ** 2) * (lcs - M) ** 2 + 2.00
    score = round(score * 4) / 4
    return min(max(score, 0.00), 2.00)


# ── SCORE SYNTAXE ────────────────────────────────────────────────────────────

def score_syntaxe(ratio_phr: float, conn_total: int, conn_categories: int) -> float:
    pts = 0.0
    if 0.15 <= ratio_phr <= 0.45:
        pts += 0.5
    if conn_categories >= 3:
        pts += 0.5
    elif conn_categories >= 2:
        pts += 0.25
    if conn_total >= 8:
        pts += 0.5
    elif conn_total >= 5:
        pts += 0.25
    return round(min(pts, 2.0), 2)


# ── SCORE ORTHOGRAPHE ────────────────────────────────────────────────────────

def _fautes_fallback(texte: str) -> dict:
    """Dictionnaire simple de fautes fréquentes si LanguageTool indisponible."""
    fautes_frequentes = [
        ("j'ai", "Verbe 'avoir' conjugué"),
        ("plutot", "Confusion 'plutôt' / 'plus tôt'"),
        ("orthografe", "Faute d'orthographe"),
        ("ereur", "Faute d'orthographe"),
        ("fote", "Faute d'orthographe"),
        ("parceque", "'parce que' s'écrit en deux mots"),
    ]
    details = []
    t = texte.lower()
    for mot, msg in fautes_frequentes:
        if mot in t:
            details.append({"message": msg, "contexte": f"...{mot}..."})
    return {"nb": len(details), "details": details}


def _fautes_languagetool(texte: str) -> dict:
    try:
        import language_tool_python
        tool = language_tool_python.LanguageTool(
            'fr', remote_server='https://api.languagetool.org/'
        )
        matches = tool.check(texte)
        details = []
        seen = set()
        for m in matches:
            ctx = m.context.strip() if m.context else ""
            suggestion = m.replacements[0] if m.replacements else ""
            key = (m.message, ctx)
            if key not in seen:
                seen.add(key)
                details.append({
                    "message": m.message,
                    "contexte": ctx,
                    "suggestion": suggestion,
                })
        return {"nb": len(details), "details": details}
    except Exception:
        return _fautes_fallback(texte)


def score_orthographe(nb_fautes: int) -> float:
    if nb_fautes > 5:
        return 0.00
    bareme = {0: 2.00, 1: 1.50, 2: 1.25, 3: 1.00, 4: 0.75, 5: 0.25}
    return bareme.get(nb_fautes, 0.00)


# ── FONCTION PRINCIPALE ──────────────────────────────────────────────────────

def evaluer_forme(
    texte_source: str,
    contraction: str,
    quota_cible: int,
    nb_mots: int
) -> dict:
    # --- Lexical ---
    lcs = lcs_score(texte_source, contraction)
    ecart_pct = abs(nb_mots - quota_cible) / max(quota_cible, 1) * 100
    penalite = penalite_quota(ecart_pct)
    score_plag = score_plagiat_parabole(lcs)
    label_plag = label_plagiat(lcs)
    score_lexical = score_plag + (1.0 - penalite)

    # --- Syntaxe ---
    phr_src = compter_phrases(texte_source)
    phr_ctr = compter_phrases(contraction)
    ratio_phr = phr_ctr / max(phr_src, 1)
    conn = analyser_connecteurs(contraction)
    score_syn = score_syntaxe(ratio_phr, conn["conn_total"], conn["conn_categories"])

    # --- Orthographe ---
    ortho = _fautes_languagetool(contraction)
    nb_fautes = ortho["nb"]
    fautes_details = ortho["details"]
    score_orth = score_orthographe(nb_fautes) * min(1.0, nb_mots / 30)

    # --- Total ---
    score_total = round(score_lexical + score_syn + score_orth, 2)

    return {
        "score_lexical":      round(score_lexical, 2),
        "score_syntaxe":      score_syn,
        "score_orthographe":  score_orth,
        "score_plagiat":      score_plag,
        "label_plagiat":      label_plag,
        "score_lcs":          round(lcs, 4),
        "penalite_quota":     penalite,
        "ecart_pct":          round(ecart_pct, 1),
        "nb_fautes":          nb_fautes,
        "fautes_details":     fautes_details,
        "connecteurs_total":  conn["conn_total"],
        "connecteurs_cat":    conn["conn_categories"],
        "ratio_phrases":      round(ratio_phr, 3),
        "score_total":        score_total,
    }
