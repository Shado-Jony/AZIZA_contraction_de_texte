"""
remplir_performances.py
=======================
1. Genere 10 contractions de qualite variee via API Mistral
2. Evalue chaque contraction via le pipeline AZIZA (import direct)
3. Ecrit data/performances/data_performances.csv

Usage :
    cd /path/to/projet
    python scripts/remplir_performances.py
"""

import csv
import os
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

TEXTES_DIR = PROJECT / "data" / "corpus" / "textes"
CSV_PATH = PROJECT / "data" / "performances" / "data_performances.csv"
MISTRAL_API_KEY = os.environ.get("MISTRAL_API_KEY", "")
TEXTES_IDS = [f"S{i:03d}" for i in range(1, 11)]

generation_prompts = [
    # 3 bonnes
    "Genere une contraction excellente : toutes les idees essentielles dans l'ordre, reformulation personnelle, connecteurs varies, zero faute, quota exact 1/4.",
    "Redige une contraction de grande qualite : fidele, fluide, bien proportionnee, vocabulaire riche, syntaxe irreprochable.",
    "Produis une contraction parfaite, tres fidele, bien structuree, avec connecteurs logiques, sans faute d'orthographe.",
    # 4 moyennes
    "Fais une contraction correcte mais basique : idees principales presentes, reformulation simple, peu de connecteurs.",
    "Redige une contraction moyenne : idees presentes mais reformulation approximative, connecteurs basiques, repetitions.",
    "Fais une contraction acceptable : structure simple, idees principales dans le desordre, style oral.",
    "Produis une contraction passable : quelques idees oubliees, phrases parfois trop proches du texte source.",
    # 3 mauvaises
    "Ecris une contraction mediocre : beaucoup d'idees manquantes, phrases proches du texte source, peu de soin.",
    "Fais une mauvaise contraction : copie des passages entiers, oublie la moitie des idees, pas de connecteurs.",
    "Produis une contraction tres mauvaise : tres peu d'idees, phrases recopiees mot pour mot, desordre total.",
]

QUALITY_LABELS = ["bonne"] * 3 + ["moyenne"] * 4 + ["mauvaise"] * 3


def charger_texte(sid):
    path = TEXTES_DIR / f"{sid}.txt"
    return path.read_text(encoding="utf-8").strip()


def generer_contraction(texte, prompt_qualite):
    if not MISTRAL_API_KEY:
        print("  MISTRAL_API_KEY non definie")
        return ""
    import requests
    payload = {
        "model": "mistral-small-latest",
        "messages": [
            {"role": "system", "content": f"{prompt_qualite}\n\nTa reponse doit contenir UNIQUEMENT la contraction, sans introduction ni commentaire."},
            {"role": "user", "content": f"TEXTE SOURCE :\n\"\"\"\n{texte[:2000]}\n\"\"\""},
        ],
        "temperature": 0.5,
        "max_tokens": 1024,
    }
    try:
        resp = requests.post(
            "https://api.mistral.ai/v1/chat/completions",
            headers={"Authorization": f"Bearer {MISTRAL_API_KEY}"},
            json=payload,
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"  Erreur generation : {e}")
        return ""


def evaluer_aziza(texte_source, contraction):
    from aziza.pipeline.complet import evaluer_complet

    if not contraction:
        return {"note_forme": 0, "note_fond": 0, "note_finale": 0}
    try:
        nb_mots = len(contraction.split())
        quota = max(1, round(len(texte_source.split()) / 4))
        res = evaluer_complet(texte_source, contraction, quota, nb_mots)
        nf = res.get("score_forme", 0)
        nd = res.get("score_fond", 0)
        return {"note_forme": nf, "note_fond": nd, "note_finale": round((nf + nd) * 2, 2)}
    except Exception as e:
        print(f"  Erreur evaluation pipeline : {e}")
        return {"note_forme": 0, "note_fond": 0, "note_finale": 0}


def main():
    if not MISTRAL_API_KEY:
        print("ERREUR : definissez MISTRAL_API_KEY dans l'environnement")
        sys.exit(1)

    rows = []
    for i, sid in enumerate(TEXTES_IDS):
        print(f"\n[{i+1}/10] {sid} ({QUALITY_LABELS[i]}) ...")
        texte_src = charger_texte(sid)
        print(f"  Texte source : {len(texte_src.split())} mots")
        print(f"  Generation contraction ...")
        contraction = generer_contraction(texte_src, generation_prompts[i])
        if not contraction:
            print("  ! Contraction vide, skip")
            continue
        wc = len(contraction.split())
        print(f"  Contraction generee : {wc} mots")
        print(f"  Evaluation via pipeline AZIZA ...")
        notes = evaluer_aziza(texte_src, contraction)
        print(f"  Forme={notes['note_forme']} Fond={notes['note_fond']} Finale={notes['note_finale']}")
        rows.append({
            "id_texte": sid,
            "contraction": contraction,
            "note_forme_expert": "",
            "note_fond_expert": "",
            "note_finale_expert": "",
            "note_forme_aziza": notes["note_forme"],
            "note_fond_aziza": notes["note_fond"],
            "note_finale_aziza": notes["note_finale"],
        })

    fieldnames = [
        "id_texte", "contraction",
        "note_forme_expert", "note_fond_expert", "note_finale_expert",
        "note_forme_aziza", "note_fond_aziza", "note_finale_aziza",
    ]
    CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CSV_PATH, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n Termine ! {len(rows)} lignes ecrites dans {CSV_PATH}")


if __name__ == "__main__":
    main()
