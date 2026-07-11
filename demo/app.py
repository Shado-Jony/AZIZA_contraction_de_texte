"""
AZIZA v2.0 — Interface Flask
=============================
Assistant Intelligent pour la Contraction de texte au BAC beninois.

Pipeline :
  Forme /7 (Lexical + Syntaxe + Orthographe) + Fond /3 (LLM Mistral)
  → Note finale /10 avec verrous plagiat et hors-sujet
"""

import os, sys, json, uuid, math
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()

import flask
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, jsonify, flash
)
from flasgger import Swagger

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "aziza-dev-key-change-in-production")

app.config["SWAGGER"] = {
    "title": "AZIZA API",
    "version": "2.0.0",
    "description": "API d'évaluation automatique de la Contraction de texte au BAC béninois",
    "openapi": "3.0.3",
}
swagger = Swagger(app)

HISTORIQUE_PATH   = Path(__file__).parent / "data" / "historique.json"
TEXTES_DIR        = PROJECT_ROOT / "data" / "corpus" / "textes"
PRODUCTIONS_DIR   = Path(__file__).parent / "data" / "productions"

MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "LR8lvqaaFuJ7TEWAVG4uR93vVdTotsvQ")
if MISTRAL_API_KEY:
    os.environ["MISTRAL_API_KEY"] = MISTRAL_API_KEY


# ── PIPELINE AZIZA v2.0 ──────────────────────────────────────────────────────

PIPELINE_OK = True
_import_error = ""

try:
    from aziza.pipeline.complet import evaluer_complet
    from aziza.machine_etats import ProfilApprenant, MachineEtats
    PIPELINE_OK = True
except ImportError as e:
    PIPELINE_OK = False
    _import_error = str(e)


def quota_depuis_source(txt):
    return max(1, round(len(txt.split()) / 4))


# Fallback classes si le pipeline n'est pas disponible
if not PIPELINE_OK:
    class ProfilApprenant:
        def __init__(self, nom, palier_actuel="decouverte", scores=None,
                     nb_exercices=0, nb_tests=0, historique_mp=None):
            self.nom = nom
            self.palier_actuel = palier_actuel
            self.scores = scores or []
            self.nb_exercices = nb_exercices
            self.nb_tests = nb_tests
            self.historique_mp = historique_mp or []
        def score_moyen_exercices(self):
            d = self.scores[-3:]
            return (sum(d) / len(d)) / 10.0 * 100.0 if d else 0.0
        def to_dict(self):
            return {"nom": self.nom, "palier_actuel": self.palier_actuel,
                    "nb_exercices": self.nb_exercices, "nb_tests": self.nb_tests,
                    "score_moyen": round(self.score_moyen_exercices(), 1)}
    class MachineEtats:
        def __init__(self, p): self.profil = p
        def enregistrer_exercice(self, s):
            self.profil.scores.append(s); self.profil.nb_exercices += 1
        def statut(self):
            return {**self.profil.to_dict(), "palier_suivant": None,
                    "seuil_progression": 75, "historique_mp": self.profil.historique_mp}
    def evaluer_complet(src, cont, quota, nb_mots):
        raise RuntimeError("Pipeline AZIZA non disponible")


# ── TEXTES SOURCES ──────────────────────────────────────────────────────────

def charger_textes_sources():
    textes = {}
    if not TEXTES_DIR.exists():
        return textes
    for fpath in sorted(TEXTES_DIR.glob("S*.txt")):
        sid = fpath.stem
        textes[sid] = {"id": sid,
                       "contenu": fpath.read_text(encoding="utf-8").strip(),
                       "titre": sid, "nb_mots": 0}
        textes[sid]["nb_mots"] = len(textes[sid]["contenu"].split())
    csv_path = TEXTES_DIR / "textes_sources.csv"
    if csv_path.exists():
        import csv as csv_mod
        with open(csv_path, encoding="utf-8-sig") as f:
            for row in csv_mod.DictReader(f):
                if row["id"] in textes:
                    textes[row["id"]]["titre"] = row.get("theme", row["id"])
    return textes

TEXTES_SOURCES = charger_textes_sources()


# ── HISTORIQUE ──────────────────────────────────────────────────────────────

def lire_historique():
    if HISTORIQUE_PATH.exists():
        try:
            data = json.loads(HISTORIQUE_PATH.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
        except (json.JSONDecodeError, ValueError):
            pass
    return []

def ecrire_historique(entries):
    HISTORIQUE_PATH.parent.mkdir(parents=True, exist_ok=True)
    HISTORIQUE_PATH.write_text(json.dumps(entries, ensure_ascii=False, indent=2),
                                encoding="utf-8")


# ── SESSION PROFIL ──────────────────────────────────────────────────────────

def get_profil():
    data = session.get("profil", {})
    return ProfilApprenant(
        nom=data.get("nom", "Eleve"),
        palier_actuel=data.get("palier_actuel", "decouverte"),
        scores=data.get("scores", []),
        nb_exercices=data.get("nb_exercices", 0),
        nb_tests=data.get("nb_tests", 0),
        historique_mp=data.get("historique_mp", []),
    )

def save_profil(profil):
    session["profil"] = {
        "nom": profil.nom, "palier_actuel": profil.palier_actuel,
        "scores": profil.scores, "nb_exercices": profil.nb_exercices,
        "nb_tests": profil.nb_tests, "historique_mp": profil.historique_mp,
    }


# ── ZONE QUOTA ──────────────────────────────────────────────────────────────

def zone_quota(ecart_pct: float) -> str:
    if ecart_pct <= 5:
        return "exact"
    elif ecart_pct <= 10:
        return "tolere"
    else:
        return "hors_quota"


# ── SAUVEGARDE PRODUCTIONS ────────────────────────────────────────────────────

def sauvegarder_production(session_id, texte_source, contraction, resultat):
    prod_dir = PRODUCTIONS_DIR / session_id
    prod_dir.mkdir(parents=True, exist_ok=True)
    (prod_dir / "source.txt").write_text(texte_source, encoding="utf-8")
    (prod_dir / "contraction.txt").write_text(contraction, encoding="utf-8")
    (prod_dir / "resultat.json").write_text(
        json.dumps(resultat, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return str(prod_dir)


# ── PIPELINE ─────────────────────────────────────────────────────────────────

def evaluer_avec_pipeline(texte_source, contraction, quota, profil):
    nb_mots = len(contraction.split())

    if not PIPELINE_OK:
        return _fallback_result(texte_source, contraction, quota, nb_mots, profil,
                                erreur=_import_error)

    try:
        res = evaluer_complet(texte_source, contraction, quota, nb_mots)

        score_global = res["note_finale"]
        score_global_pct = round(score_global / 10.0 * 100.0, 1)

        # Machine à états : enregistrer_exercice attend un score sur 10
        machine = MachineEtats(profil)
        machine.enregistrer_exercice(min(10, max(0, round(score_global))))
        statut = machine.statut()

        return {
            "nb_mots":            nb_mots,
            "quota_cible":        quota,
            "ecart_pct":          res["ecart_pct"],
            "zone_quota":         zone_quota(res["ecart_pct"]),
            "score_lexical":      res["score_lexical"],
            "score_syntaxe":      res["score_syntaxe"],
            "score_orthographe":  res["score_orthographe"],
            "score_forme":        res["score_forme"],
            "score_plagiat":      res["score_plagiat"],
            "score_lcs":          res["score_lcs"],
            "penalite_quota":     res["penalite_quota"],
            "nb_fautes":          res["nb_fautes"],
            "fautes_details":     res["fautes_details"],
            "connecteurs_total":  res["connecteurs_total"],
            "connecteurs_cat":    res["connecteurs_cat"],
            "ratio_phrases":      res["ratio_phrases"],

            "score_fond":         res["score_fond"],
            "score_fond_brut":    res["score_fond_brut"],
            "contresens":         res["contresens_detecte"],
            "subjectivite_detectee": res["subjectivite_detectee"],
            "phrase_subjective":  res["phrase_subjective"],
            "idees_manquantes":   res["idees_manquantes"],
            "score_semantique":   res["score_semantique"],
            "raisonnement":       res["raisonnement"],
            "feedback_erreur":    res["feedback_erreur"],
            "feedback_mc":        res["feedback_micro_cours"],
            "feedback_exemple":   res["feedback_exemple"],

            "verrou_plagiat":     res["verrou_plagiat"],
            "verrou_hors_sujet":  res["verrou_hors_sujet"],
            "verrou_trop_court":  res["verrou_trop_court"],

            "score_global":       score_global,
            "score_global_pct":   score_global_pct,
            "palier_actuel":      profil.palier_actuel,
            "mp":                 profil.historique_mp[-1] if profil.historique_mp else 0,
            "palier_suivant":     statut.get("palier_suivant"),
            "progression": {
                "historique_mp":  profil.historique_mp,
                "score_moyen":    round(profil.score_moyen_exercices(), 1),
            },
        }
    except Exception as e:
        return _fallback_result(texte_source, contraction, quota, nb_mots, profil,
                                erreur=str(e))


def _fallback_result(texte_source, contraction, quota, nb_mots, profil, erreur=""):
    ecart_pct = abs(nb_mots - quota) / max(quota, 1) * 100
    return {
        "nb_mots": nb_mots, "quota_cible": quota,
        "ecart_pct": round(ecart_pct, 2),
        "zone_quota": zone_quota(ecart_pct),
        "score_lexical": 0, "score_syntaxe": 0, "score_orthographe": 0,
        "score_forme": 0, "score_plagiat": 0,
        "score_lcs": 0.0, "penalite_quota": 0, "nb_fautes": 0, "fautes_details": [],
        "connecteurs_total": 0, "connecteurs_cat": 0, "ratio_phrases": 0.0,
        "score_fond": 0, "score_fond_brut": 0,
        "contresens": False, "subjectivite_detectee": False,
        "phrase_subjective": "", "idees_manquantes": [],
        "score_semantique": 0.0,
        "raisonnement": "", "feedback_erreur": erreur or "Erreur lors de l'evaluation.",
        "feedback_mc": "Reessayez ou contactez l'administrateur.",
        "feedback_exemple": "",
        "verrou_plagiat": False, "verrou_hors_sujet": False, "verrou_trop_court": False,
        "score_global": 0, "score_global_pct": 0,
        "palier_actuel": profil.palier_actuel,
        "mp": 0, "palier_suivant": None,
        "progression": {"historique_mp": [], "score_moyen": 0},
    }


# ── ROUTES ──────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return redirect(url_for("soumission"))


@app.route("/soumission")
def soumission():
    """Formulaire de soumission d'une contraction.
    ---
    get:
      summary: Affiche le formulaire de soumission
      responses:
        200:
          description: Page HTML du formulaire
    """
    profil = get_profil()
    return render_template("soumission.html", textes=TEXTES_SOURCES,
                           profil=profil.to_dict() if profil.nom else None,
                           has_api_key=bool(MISTRAL_API_KEY),
                           pipeline_ok=PIPELINE_OK)


@app.route("/evaluer", methods=["POST"])
def evaluer():
    """Évalue une contraction de texte.
    ---
    post:
      summary: Lance le pipeline d'évaluation complet
      requestBody:
        required: true
        content:
          application/x-www-form-urlencoded:
            schema:
              type: object
              properties:
                texte_source:
                  type: string
                  description: Texte source à contracter
                contraction:
                  type: string
                  description: Texte produit par l'élève
                quota_cible:
                  type: integer
                  description: Nombre de mots cible (optionnel, auto-calculé)
      responses:
        302:
          description: Redirection vers /resultats/<session_id>
    """
    texte_source = request.form.get("texte_source", "").strip()
    contraction  = request.form.get("contraction", "").strip()
    quota_str    = request.form.get("quota_cible", "").strip()

    if not texte_source or not contraction:
        flash("Veuillez fournir un texte source et une contraction.", "error")
        return redirect(url_for("soumission"))

    quota = (quota_depuis_source(texte_source) if not quota_str
             else (int(quota_str) if quota_str.isdigit() else quota_depuis_source(texte_source)))

    profil = get_profil()
    resultat = evaluer_avec_pipeline(texte_source, contraction, quota, profil)
    resultat["timestamp"] = datetime.now().isoformat()

    session_id = str(uuid.uuid4())[:8]
    resultat["session_id"] = session_id
    resultat["texte_source_extrait"] = (texte_source[:200] + "..."
                                        if len(texte_source) > 200 else texte_source)
    resultat["contraction_extrait"] = (contraction[:200] + "..."
                                       if len(contraction) > 200 else contraction)

    prod_dir = sauvegarder_production(session_id, texte_source, contraction, resultat)
    resultat["production_dir"] = prod_dir
    save_profil(profil)

    historique = lire_historique()
    historique.append({
        "session_id": session_id,
        "production_dir": prod_dir,
        "timestamp": resultat["timestamp"],
        "score_global": resultat["score_global"],
        "score_global_pct": resultat["score_global_pct"],
        "score_forme": resultat["score_forme"],
        "score_fond": resultat["score_fond"],
        "score_lexical": resultat.get("score_lexical", 0),
        "score_syntaxe": resultat.get("score_syntaxe", 0),
        "score_orthographe": resultat.get("score_orthographe", 0),
        "score_semantique": resultat.get("score_semantique", 0),
        "label_plagiat": resultat.get("label_plagiat", "original"),
        "zone_quota": resultat.get("zone_quota", "hors_quota"),
        "palier_actuel": resultat["palier_actuel"],
        "mp": resultat.get("mp", 0),
        "contresens": resultat["contresens"],
        "subjectivite_detectee": resultat.get("subjectivite_detectee", False),
        "verrou_plagiat": resultat["verrou_plagiat"],
        "verrou_hors_sujet": resultat.get("verrou_hors_sujet", False),
        "verrou_trop_court": resultat.get("verrou_trop_court", False),
        "nb_mots": resultat.get("nb_mots", 0),
        "quota_cible": resultat.get("quota_cible", 0),
        "ecart_pct": resultat.get("ecart_pct", 0),
        "penalite_quota": resultat.get("penalite_quota", 0),
        "nb_fautes": resultat.get("nb_fautes", 0),
        "score_lcs": resultat.get("score_lcs", 0),
        "connecteurs_total": resultat.get("connecteurs_total", 0),
        "connecteurs_cat": resultat.get("connecteurs_cat", 0),
        "ratio_phrases": resultat.get("ratio_phrases", 0.0),
        "score_fond_brut": resultat.get("score_fond_brut", 0),
        "phrase_subjective": resultat.get("phrase_subjective", ""),
        "idees_manquantes": resultat.get("idees_manquantes", []),
        "feedback_erreur": resultat.get("feedback_erreur", ""),
        "feedback_mc": resultat.get("feedback_mc", ""),
        "feedback_exemple": resultat.get("feedback_exemple", ""),
        "raisonnement": resultat.get("raisonnement", ""),
    })
    ecrire_historique(historique)

    session["last_result"] = resultat
    return redirect(url_for("resultats", session_id=session_id))


@app.route("/resultats/<session_id>")
def resultats(session_id):
    resultat = session.get("last_result")
    if not resultat or resultat.get("session_id") != session_id:
        for entry in lire_historique():
            if entry["session_id"] == session_id:
                flash("Details de cette evaluation plus en memoire.", "info")
                return redirect(url_for("progression"))
        flash("Session introuvable.", "error")
        return redirect(url_for("soumission"))

    profil = get_profil()
    labels = {"decouverte": "Decouverte", "consolidation": "Consolidation", "maitrise": "Maitrise"}
    return render_template("resultats.html", r=resultat, profil=profil.to_dict(),
                           palier_label=labels.get(resultat["palier_actuel"], resultat["palier_actuel"]),
                           has_api_key=bool(MISTRAL_API_KEY))


@app.route("/pdf/<session_id>")
def fiche_note(session_id):
    entry = None
    for e in lire_historique():
        if e["session_id"] == session_id:
            entry = e
            break
    if not entry:
        flash("Session introuvable.", "error")
        return redirect(url_for("progression"))

    prod_dir = Path(entry.get("production_dir", ""))
    texte_source = (prod_dir / "source.txt").read_text(encoding="utf-8") if prod_dir.exists() else ""
    contraction  = (prod_dir / "contraction.txt").read_text(encoding="utf-8") if prod_dir.exists() else ""

    profil = get_profil()
    labels = {"decouverte": "Decouverte", "consolidation": "Consolidation", "maitrise": "Maitrise"}
    return render_template("fiche_note.html", r=entry, texte_source=texte_source,
                           contraction=contraction, profil=profil.to_dict(),
                           palier_label=labels.get(entry["palier_actuel"], entry["palier_actuel"]))


@app.route("/progression")
def progression():
    historique = lire_historique()
    profil = get_profil()
    labels = {"decouverte": "Decouverte", "consolidation": "Consolidation", "maitrise": "Maitrise"}
    couleurs = {"decouverte": "#e74c3c", "consolidation": "#f39c12", "maitrise": "#2ecc71"}
    machine = MachineEtats(profil)
    statut = machine.statut()
    stats = {
        "total": len(historique),
        "moyenne": round(sum(e["score_global"] for e in historique) / len(historique), 1) if historique else 0,
        "meilleur": max((e["score_global"] for e in historique), default=0),
        "dernier": historique[-1] if historique else None,
    }
    return render_template("progression.html", historique=historique, profil=profil.to_dict(),
                           statut=statut, stats=stats, palier_labels=labels, palier_couleurs=couleurs,
                           historique_json=json.dumps(historique, ensure_ascii=False))


@app.route("/demarrer", methods=["POST"])
def demarrer():
    nom = request.form.get("nom", "Eleve").strip() or "Eleve"
    profil = ProfilApprenant(nom=nom)
    save_profil(profil)
    flash("Bienvenue, {} ! Pret a travailler votre contraction de texte.".format(nom), "success")
    return redirect(url_for("soumission"))


@app.route("/reset", methods=["POST"])
def reset():
    session.pop("profil", None)
    session.pop("last_result", None)
    HISTORIQUE_PATH.write_text("[]", encoding="utf-8")
    flash("Progression reinitialisee. Vous repartez a zero.", "info")
    return redirect(url_for("soumission"))


# ── LANCEMENT ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("AZIZA v2.0 - Interface d'evaluation")
    print("Contraction de texte - BAC beninois\n")
    if MISTRAL_API_KEY:
        print("[OK] API Mistral : configuree")
    else:
        print("[ATTENTION] API Mistral : NON configuree")
        print("  -> Evaluation du fond desactivee.")
    if PIPELINE_OK:
        print("[OK] Pipeline AZIZA v2.0 : importe")
    else:
        print("[ERREUR] Pipeline AZIZA :", _import_error)
    print("{} textes sources charges".format(len(TEXTES_SOURCES)))
    print("http://127.0.0.1:5100")
    app.run(debug=True, port=5100)
