"""
demo/api.py — API REST AZIZA v2.0
==================================
Blueprints :
  POST /api/v1/evaluer  → JSON complet d'évaluation (token requis)
  GET  /api/v1/health   → {"status": "ok"}
"""

import sys
from pathlib import Path

from flask import Blueprint, request, jsonify, g

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aziza.pipeline.complet import evaluer_complet
from demo.token_manager import validate_token, increment_usage

api_bp = Blueprint("api", __name__, url_prefix="/api/v1")


def require_token():
    token = request.headers.get("X-API-Key", "")
    result = validate_token(token)
    if not result["ok"]:
        return result
    g.api_token = token
    g.api_client = result["client_name"]
    g.api_plan = result["plan"]
    g.api_limit = result["limit"]
    g.api_used = result["used"]
    g.api_remaining = result["remaining"]
    return None


@api_bp.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "version": "2.0.0"})


@api_bp.route("/evaluer", methods=["POST"])
def evaluer():
    auth = require_token()
    if auth:
        return jsonify({"error": auth["error"]}), auth["status"]

    body = request.get_json(silent=True)
    if not body:
        return jsonify({"error": "Corps JSON invalide ou manquant."}), 400

    texte_source = (body.get("texte_source") or "").strip()
    contraction = (body.get("contraction") or "").strip()

    if not texte_source or not contraction:
        return jsonify({
            "error": "Champs obligatoires : texte_source, contraction."
        }), 400

    quota_str = body.get("quota_cible")
    quota_cible = int(quota_str) if quota_str and str(quota_str).isdigit() else None

    nb_mots = len(contraction.replace("'", " ").split())
    if quota_cible is None:
        quota_cible = max(1, round(len(texte_source.replace("'", " ").split()) / 4))

    try:
        res = evaluer_complet(texte_source, contraction, quota_cible, nb_mots)
        note_finale = res["note_finale"]

        increment_usage(g.api_token)

        return jsonify({
            "succes": True,
            "note_finale": note_finale,
            "score_forme": res["score_forme"],
            "score_fond": res["score_fond"],
            "score_lexical": res["score_lexical"],
            "score_syntaxe": res["score_syntaxe"],
            "score_orthographe": res["score_orthographe"],
            "score_fond_brut": res["score_fond_brut"],
            "score_semantique": res["score_semantique"],
            "score_plagiat": res["score_plagiat"],
            "score_lcs": res["score_lcs"],
            "ecart_pct": res["ecart_pct"],
            "penalite_quota": res["penalite_quota"],
            "nb_fautes": res["nb_fautes"],
            "connecteurs_total": res["connecteurs_total"],
            "connecteurs_cat": res["connecteurs_cat"],
            "ratio_phrases": res["ratio_phrases"],
            "contresens_detecte": res["contresens_detecte"],
            "subjectivite_detectee": res["subjectivite_detectee"],
            "phrase_subjective": res["phrase_subjective"],
            "idees_manquantes": res["idees_manquantes"],
            "verrou_plagiat": res["verrou_plagiat"],
            "verrou_hors_sujet": res["verrou_hors_sujet"],
            "verrou_trop_court": res["verrou_trop_court"],
            "raisonnement": res["raisonnement"],
            "feedback_erreur": res["feedback_erreur"],
            "feedback_micro_cours": res["feedback_micro_cours"],
            "feedback_exemple": res["feedback_exemple"],
            "quota_plan": {
                "plan": g.api_plan,
                "limite": g.api_limit,
                "utilise": g.api_used,
                "restant": g.api_remaining,
            },
        })
    except Exception as e:
        return jsonify({
            "succes": False,
            "error": "Erreur lors de l'évaluation.",
            "detail": str(e),
        }), 500
