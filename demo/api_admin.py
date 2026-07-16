"""
demo/api_admin.py — Administration des tokens API
==================================================
Protégé par la clé maître AZIZA_API_KEY (variable d'environnement).

Routes :
  GET    /admin/tokens              → liste des tokens
  POST   /admin/tokens              → créer un nouveau token
  PATCH  /admin/tokens/<token>/plan → changer le plan
  DELETE /admin/tokens/<token>      → désactiver un token
"""

import os

from flask import Blueprint, request, jsonify

from demo.token_manager import (
    create_token,
    list_tokens,
    deactivate_token,
    change_plan,
    PLANS,
)

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")

MASTER_KEY = os.environ.get("AZIZA_API_KEY", "aziza-api-key-2026")


def require_master():
    key = request.headers.get("X-API-Key", "")
    if key != MASTER_KEY:
        return jsonify({"error": "Non autorisé. Clé maître invalide."}), 401
    return None


@admin_bp.route("/tokens", methods=["GET"])
def lister_tokens():
    auth = require_master()
    if auth:
        return auth
    only_active = request.args.get("active", "").lower() in ("1", "true", "yes")
    tokens = list_tokens(only_active=only_active)
    return jsonify({"count": len(tokens), "tokens": tokens})


@admin_bp.route("/tokens", methods=["POST"])
def creer_token():
    auth = require_master()
    if auth:
        return auth
    body = request.get_json(silent=True)
    if not body:
        return jsonify({"error": "Corps JSON invalide."}), 400
    client_name = (body.get("client_name") or "").strip()
    if not client_name:
        return jsonify({"error": "Champ requis : client_name"}), 400
    plan = (body.get("plan") or "free").strip()
    if plan not in PLANS:
        return jsonify({"error": f"Plan invalide. Options : {list(PLANS)}"}), 400
    token = create_token(client_name, plan)
    return jsonify({"succes": True, "token": token}), 201


@admin_bp.route("/tokens/<token>/plan", methods=["PATCH"])
def modifier_plan(token):
    auth = require_master()
    if auth:
        return auth
    body = request.get_json(silent=True)
    if not body:
        return jsonify({"error": "Corps JSON invalide."}), 400
    new_plan = (body.get("plan") or "").strip()
    if new_plan not in PLANS:
        return jsonify({"error": f"Plan invalide. Options : {list(PLANS)}"}), 400
    try:
        result = change_plan(token, new_plan)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    if result is None:
        return jsonify({"error": "Token introuvable."}), 404
    return jsonify({"succes": True, "token": result})


@admin_bp.route("/tokens/<token>", methods=["DELETE"])
def desactiver_token(token):
    auth = require_master()
    if auth:
        return auth
    ok = deactivate_token(token)
    if not ok:
        return jsonify({"error": "Token introuvable."}), 404
    return jsonify({"succes": True, "message": "Token désactivé."})
