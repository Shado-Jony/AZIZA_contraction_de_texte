"""
aziza/pipeline/similarite.py
=============================
Métriques de similarité textuelle pour la détection du plagiat
dans la Contraction de texte au BAC béninois.

Métrique retenue : LCS normalisée (Exp. 1, 2, 4)
Seuils v2.0 : Smin = 0.26 (hors-sujet), Smax = 0.80 (plagiat)
"""

import re
import json
from pathlib import Path
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


_SEUILS_PATH = Path(__file__).parent / "seuils_production.json"

def _load_seuils() -> dict:
    with open(_SEUILS_PATH, encoding="utf-8") as f:
        return json.load(f)

SEUILS = _load_seuils()
SEUIL_LCS       = SEUILS["metriques"]["lcs"]["seuil_similaire"]     # 0.577
SEUIL_PLAGIAT   = SEUILS["metriques"]["lcs"]["seuil_plagiat"]       # 0.80
SMIN            = SEUILS["metriques"]["lcs"]["smin"]                 # 0.26


def tokenize(text: str) -> list[str]:
    text = text.lower()
    text = re.sub(r"[''`\u2019\u2018]", " ", text)
    return re.findall(r"\b[a-záàâäéèêëíìîïóòôöúùûüýÿæœçñ]+\b", text)


def ngrams(tokens: list[str], n: int = 2) -> list[tuple]:
    return [tuple(tokens[i:i+n]) for i in range(len(tokens) - n + 1)]


def lcs_score(text1: str, text2: str) -> float:
    t1 = tokenize(text1)
    t2 = tokenize(text2)
    if not t1 or not t2:
        return 0.0
    prev = [0] * (len(t2) + 1)
    for w1 in t1:
        curr = [0] * (len(t2) + 1)
        for j, w2 in enumerate(t2, 1):
            curr[j] = prev[j-1] + 1 if w1 == w2 else max(prev[j], curr[j-1])
        prev = curr
    return prev[-1] / len(t2)


def jaccard_bigrams(text1: str, text2: str) -> float:
    bg1 = set(ngrams(tokenize(text1), 2))
    bg2 = set(ngrams(tokenize(text2), 2))
    if not bg1 or not bg2:
        return 0.0
    return len(bg1 & bg2) / len(bg1 | bg2)


def cosinus_tfidf(text1: str, text2: str) -> float:
    vectorizer = TfidfVectorizer(
        analyzer="word",
        ngram_range=(1, 2),
        min_df=1,
        token_pattern=r"\b[a-záàâäéèêëíìîïóòôöúùûüýÿæœçñ]+\b"
    )
    try:
        tfidf = vectorizer.fit_transform([text1.lower(), text2.lower()])
        return float(cosine_similarity(tfidf[0:1], tfidf[1:2])[0][0])
    except Exception:
        return 0.0


def score_plagiat_parabole(lcs: float) -> float:
    if lcs < SMIN or lcs >= SEUIL_PLAGIAT:
        return 0.0
    M = (SMIN + SEUIL_PLAGIAT) / 2
    H = (SEUIL_PLAGIAT - SMIN) / 2
    score = -1.50 / (H ** 2) * (lcs - M) ** 2 + 2.00
    score = round(score * 4) / 4
    return min(max(score, 0.00), 2.00)


def label_plagiat(score: float) -> str:
    if score >= SEUIL_PLAGIAT:
        return "plagiat"
    elif score >= SEUIL_LCS:
        return "similaire"
    else:
        return "original"


def analyser_similarite(texte_source: str, contraction: str) -> dict:
    score_lcs     = lcs_score(texte_source, contraction)
    score_jaccard = jaccard_bigrams(texte_source, contraction)
    score_tfidf   = cosinus_tfidf(texte_source, contraction)
    score_parab   = score_plagiat_parabole(score_lcs)

    return {
        "score_lcs":       round(score_lcs,     4),
        "score_jaccard":   round(score_jaccard, 4),
        "score_tfidf":     round(score_tfidf,   4),
        "score_plagiat":   round(score_parab,   2),
        "label_plagiat":   label_plagiat(score_lcs),
        "seuil_lcs":       SEUIL_LCS,
        "seuil_plagiat":   SEUIL_PLAGIAT,
        "smin":            SMIN,
    }
