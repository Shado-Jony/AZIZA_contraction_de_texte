# AZIZA — Assistant Intelligent pour la Contraction de Texte au BAC Béninois

**Version 2.0** — Pipeline NLP hybride d'évaluation automatique avec correction forme/fond, verrous pédagogiques, et interface web Flask.

AZIZA (Zone d'Apprentissage et l'Excellence Académique) est un moteur IA conçu pour noter automatiquement les épreuves de contraction de texte du Baccalauréat béninois. Il combine des métriques lexicales classiques, une analyse linguistique outillée (LanguageTool), et un LLM (Mistral AI) pour une évaluation en deux axes : **Forme (/7)** et **Fond (/3)**, fusionnés en une note finale **/10**.

---

## Architecture du scoring

```
                    ┌─────────────────────────┐
                    │     Note finale /10      │
                    └──────────┬───────────────┘
                               │
              ┌────────────────┼────────────────┐
              │                                   │
         Forme /7                              Fond /3
     (métriques fermées)                   (LLM Mistral)
              │                                   │
    ┌─────────┼──────────┐           ┌────────────┼────────────┐
    │         │          │           │            │            │
  Lexical   Syntaxe  Orthographe   Sémantique   LLM Few-Shot   Calibration
    /3        /2        /2        (embedding)  (CoT + 5 ex.)  + Subjectivité
```

### Forme (/7) — Métriques déterministes

| Composante | Note | Méthode |
|------------|------|---------|
| **Lexical** | /3 | LCS normalisé + fonction parabolique (Smin=0.26, Smax=0.80) + pénalité quota continue `min(2, ecart_pct/50)` |
| **Syntaxe** | /2 | Ratio de phrases (src/ctr) + connecteurs logiques (9 catégories) |
| **Orthographe** | /2 | LanguageTool API distant + barème dégressif × `min(1, nb_mots/30)` + affichage détaillé des erreurs |

### Fond (/3) — Évaluation LLM

| Composante | Note | Méthode |
|------------|------|---------|
| **Similarité sémantique** | — | `mistral-embed`, seuil hors-sujet < 0.85 |
| **Raisonnement & contresens** | /3 | `mistral-small-latest`, prompt Few-Shot + CoT + 5 exemples |
| **Subjectivité** | −1pt | Détection des pronoms personnels (je, moi, mon…) et expressions d'opinion (à mon avis, selon moi, je pense…) |

### Verrous pédagogiques

| Verrou | Déclencheur | Effet |
|--------|-------------|-------|
| **Plagiat** | LCS ≥ 0.80 | Note globale = **0/10** |
| **Hors-sujet** | Sémantique < 0.85 | Fond = 0/3, pénalité Forme -1pt |
| **Texte trop court** | `nb_mots < 20` | Note globale = **0/10** |
| **Subjectivité** | Phrase avec opinion personnelle (je, à mon avis…) | Fond −1pt |

---

## Démarrage rapide

```bash
git clone <votre-repo>
cd AZIZA

# 1. Installer les dépendances
pip install -r requirements.txt

# 2. Configurer la clé API
cp .env.example .env
# Éditer .env et y mettre votre clé Mistral (voir https://console.mistral.ai/)

# 3. Lancer l'application
python demo/app.py
# → http://127.0.0.1:5100
```

### Avec Docker

```bash
docker compose up --build
# → http://localhost:5100
```

### Documentation API (Swagger)

Une fois l'application lancée :

```
http://localhost:5100/apidocs
```

Interface Swagger UI interactive pour explorer les endpoints.

---

## Tests

```bash
# Tests unitaires rapides (110 tests, sans API)
python tests.py

# Tests d'intégration (inclut API Mistral)
python tests.py all
```

Les tests sont automatisés via **GitHub Actions** sur chaque push (`.github/workflows/ci.yml`).

---

## Structure du projet

```
AZIZA/
├── aziza/                           # Moteur IA
│   ├── __init__.py                  # v2.0.0
│   ├── pipeline/                    # Pipeline d'évaluation
│   │   ├── complet.py               # Orchestrateur : fusion forme + fond + verrous
│   │   ├── forme.py                 # Évaluation de la forme (/7)
│   │   ├── fond.py                  # Évaluation du fond (/3) via Mistral
│   │   ├── similarite.py            # Métriques lexicales (LCS, Jaccard, TF-IDF, parabole)
│   │   └── seuils_production.json   # Seuils v2.0
│   └── machine_etats.py             # Machine à états adaptative (3 paliers)
│
├── demo/                            # Interface web Flask
│   ├── app.py                       # Routes, session, historique, Swagger
│   ├── static/
│   │   └── style.css                # Styles professionnels
│   ├── templates/
│   │   ├── soumission.html          # Formulaire d'évaluation
│   │   ├── resultats.html           # Résultats avec breakdown forme/fond
│   │   ├── progression.html         # Historique, graphiques Chart.js, radar
│   │   └── fiche_note.html          # Fiche imprimable/PDF
│   └── data/                        # Stockage automatique
│       ├── historique.json          # Historique des évaluations
│       └── productions/             # Textes sources + contractions bruts
│
├── .github/workflows/
│   └── ci.yml                       # CI : tests unitaires + intégration + Docker
│
├── .env.example                     # Variables d'environnement (template)
├── .gitignore
├── Dockerfile                       # Image Docker production
├── docker-compose.yml               # Orchestration Docker
├── requirements.txt                 # Dépendances Python
├── tests.py                         # 110 tests unitaires + intégration
└── README.md                        # Ce fichier
```

---

## Configuration

Copier `.env.example` vers `.env` et ajuster :

```ini
MISTRAL_API_KEY=votre_cle_api_mistral    # Obligatoire pour le Fond /3
FLASK_SECRET_KEY=une_cle_secrete_unique   # Changez en production
FLASK_ENV=production                      # development / production
FLASK_PORT=5100                           # Port d'écoute
```

---

## Graphiques de progression

La page `/progression` affiche (via Chart.js) :
- **3 courbes d'évolution** : Note globale /10, Forme /7, Fond /3
- **Radar des compétences** : Lexical, Syntaxe, Orthographe, Sémantique, Connecteurs

---

## Déploiement

### Render / HuggingFace Spaces

```yaml
# render.yaml (ou Docker)
startCommand: python demo/app.py
envVars:
  - key: MISTRAL_API_KEY
    value: votre_clé
```

### VPS avec Docker

```bash
docker compose up -d
```

---

## Expérimentation et validation

6 notebooks d'expérimentation ont été réalisés sur un corpus réel :

| Expérience | Composante | Métrique clé | Résultat |
|------------|-----------|--------------|----------|
| EDA | Corpus | Statistiques descriptives | — |
| Forme 1 | Lexical | Smin=0.26, Smax=0.80 | Fonction parabolique validée |
| Forme 2 | Syntaxe + Ortho | LanguageTool, connecteurs | Barème dégressif |
| Forme 3 | Fusion Forme /7 | Pearson r=0.636 | Corrélation modérée |
| Fond 1 | Embeddings Mistral | Smin_sem=0.85 | Seuil hors-sujet |
| Fond 2 | LLM Few-Shot /3 | Pearson r=0.860, F1 contresens=0.77 | Très forte corrélation |
| Globale | Fusion /10 | **Pearson r=0.797**, **Weighted Kappa=0.776** | Accord substantiel |

Rapport de synthèse : `experiments/resultats/forme_et_fond/rapport_synthese.md`

---

## Stack technique

| Technologie | Usage |
|-------------|-------|
| **Python 3.12+** | Langage hôte |
| **Flask** | Interface web |
| **Mistral AI API** | Embeddings (`mistral-embed`) + LLM (`mistral-small-latest`) |
| **LanguageTool** | Correction orthographique distante |
| **scikit-learn** | TF-IDF, similarité cosinus |
| **Chart.js** | Graphiques de progression (CDN) |
| **Docker** | Conteneurisation |
| **GitHub Actions** | CI/CD |

---

## Licence

Projet académique — utilisation dans le cadre de l'évaluation de la Contraction de texte au Baccalauréat béninois.
