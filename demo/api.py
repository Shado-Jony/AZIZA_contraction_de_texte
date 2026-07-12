"""
demo/api.py — API REST AZIZA v2.0
==================================
Blueprints :
  POST /api/v1/evaluer  → JSON complet d'évaluation (clé API requise)
  GET  /api/v1/health   → {"status": "ok"}
"""

import os
import sys
from pathlib import Path

from flask import Blueprint, request, jsonify
from flask_limiter import Limiter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aziza.pipeline.complet import evaluer_complet

api_bp = Blueprint("api", __name__, url_prefix="/api/v1")


def _rate_key():
    return request.headers.get("X-API-Key", request.remote_addr)


limiter = Limiter(key_func=_rate_key)

AZIZA_API_KEY = os.environ.get(
    "AZIZA_API_KEY", "aziza-api-key-2026"
)


def require_api_key():
    key = request.headers.get("X-API-Key", "")
    if key != AZIZA_API_KEY:
        return jsonify({"error": "Unauthorized", "message": "Clé API invalide ou manquante."}), 401
    return None


@api_bp.route("/health", methods=["GET"])
def health():
    """Healthcheck public de l'API.
    ---
    get:
      summary: Vérifie que l'API est opérationnelle
      responses:
        200:
          description: API en ligne
          content:
            application/json:
              schema:
                type: object
                properties:
                  status:
                    type: string
                    example: ok
    """
    return jsonify({"status": "ok", "version": "2.0.0"})


@api_bp.route("/evaluer", methods=["POST"])
@limiter.limit("60/minute")
def evaluer():
    """Évalue une contraction de texte via l'API REST.
    ---
    post:
      summary: Évalue une contraction (JSON)
      description: >
        Pipeline complet forme /7 + fond /3 + verrous.
        Nécessite un header X-API-Key valide.
        Limité à 60 requêtes/min.
      security:
        - ApiKeyAuth: []
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [texte_source, contraction]
              properties:
                texte_source:
                  type: string
                  description: Texte source à contracter
                contraction:
                  type: string
                  description: Texte produit par l'élève
                quota_cible:
                  type: integer
                  description: Nombre de mots cible (optionnel)
      responses:
        200:
          description: Résultat complet de l'évaluation
          content:
            application/json:
              schema:
                type: object
        401:
          description: Clé API invalide
        429:
          description: Trop de requêtes (rate limit)
    """
    auth = require_api_key()
    if auth:
        return auth

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

    nb_mots = len(contraction.split())
    if quota_cible is None:
        quota_cible = max(1, round(len(texte_source.split()) / 4))

    try:
        res = evaluer_complet(texte_source, contraction, quota_cible, nb_mots)
        note_finale = res["note_finale"]

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
        })
    except Exception as e:
        return jsonify({
            "succes": False,
            "error": "Erreur lors de l'évaluation.",
            "detail": str(e),
        }), 500
