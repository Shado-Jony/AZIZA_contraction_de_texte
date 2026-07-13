"""
aziza/pipeline/complet.py
==========================
Pipeline complet AZIZA v2.0.

Étapes :
  1. Évaluer la FORME (/7) via forme.evaluer_forme()
  2. Évaluer le FOND (/3) via fond.evaluer_fond()
  3. Appliquer les verrous (plagiat, hors-sujet)
  4. Calculer la note finale /10

Retourne un dictionnaire complet pour l'affichage.
"""

import json
from pathlib import Path
from .forme import evaluer_forme
from .fond  import evaluer_fond

_SEUILS_PATH = Path(__file__).parent / "seuils_production.json"
with open(_SEUILS_PATH) as f:
    _SEUILS = json.load(f)
SMIN_SEM = _SEUILS["metriques"]["semantique"]["smin_sem"]


def evaluer_complet(
    texte_source: str,
    contraction: str,
    quota_cible: int,
    nb_mots: int
) -> dict:
    # --- Étape 1 : FORME /7 ---
    forme = evaluer_forme(texte_source, contraction, quota_cible, nb_mots)

    # --- Étape 2 : FOND /3 ---
    fond = evaluer_fond(texte_source, contraction)

    # --- Étape 3 : Verrous ---
    verrou_plagiat = forme["score_plagiat"] == 0.0
    verrou_hors_sujet = fond["score_semantique"] < SMIN_SEM
    NB_MOTS_MIN = _SEUILS.get("barème_notation", {}).get("verrous", {}).get("nb_mots_min", 20)
    verrou_trop_court = nb_mots < NB_MOTS_MIN

    score_forme = forme["score_total"]
    score_fond  = fond["score_fond_calibre"]

    if verrou_plagiat:
        score_forme = 0.0
        score_fond  = 0.0

    if verrou_hors_sujet:
        score_fond = 0.0
        score_forme = max(0.0, score_forme - 1.0)

    if verrou_trop_court:
        score_forme = 0.0
        score_fond = 0.0

    # --- Étape 4 : Note finale ---
    note_finale = round(score_forme + score_fond, 2)

    return {
        # Résultats forme
        "score_lexical":        forme["score_lexical"],
        "score_syntaxe":        forme["score_syntaxe"],
        "score_orthographe":    forme["score_orthographe"],
        "score_plagiat":        forme["score_plagiat"],
        "label_plagiat":        forme["label_plagiat"],
        "score_lcs":            forme["score_lcs"],
        "penalite_quota":       forme["penalite_quota"],
        "ecart_pct":            forme["ecart_pct"],
        "nb_fautes":            forme["nb_fautes"],
        "fautes_details":       forme["fautes_details"],
        "connecteurs_total":    forme["connecteurs_total"],
        "connecteurs_cat":      forme["connecteurs_cat"],
        "ratio_phrases":        forme["ratio_phrases"],

        # Résultats fond
        "score_fond_brut":      fond["score_fond_brut"],
        "score_fond_calibre":   fond["score_fond_calibre"],
        "contresens_detecte":   fond["contresens_detecte"],
        "subjectivite_detectee": fond["subjectivite_detectee"],
        "phrase_subjective":    fond["phrase_subjective"],
        "idees_manquantes":     fond["idees_manquantes"],
        "score_semantique":     fond["score_semantique"],
        "raisonnement":         fond["raisonnement"],
        "feedback_erreur":      fond["feedback_erreur"],
        "feedback_micro_cours": fond["feedback_micro_cours"],
        "feedback_exemple":     fond["feedback_exemple"],

        # Verrous
        "verrou_plagiat":       verrou_plagiat,
        "verrou_hors_sujet":    verrou_hors_sujet,
        "verrou_trop_court":    verrou_trop_court,

        # Scores finaux
        "score_forme":          round(score_forme, 2),
        "score_fond":           round(score_fond, 2),
        "note_finale":          note_finale,
    }
