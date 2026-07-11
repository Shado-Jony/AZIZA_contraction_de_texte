"""
AZIZA v2.0 — Tests unitaires et d'intégration
===============================================
Exécution rapide :   python tests.py
Exécution complète : python tests.py all
"""

import sys, pathlib, os, unittest, json
from unittest.mock import patch, MagicMock
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from aziza.pipeline.similarite import (
    lcs_score, jaccard_bigrams, cosinus_tfidf,
    score_plagiat_parabole, label_plagiat, SMIN, SEUIL_PLAGIAT,
    tokenize, ngrams, analyser_similarite
)
from aziza.pipeline.forme import (
    compter_phrases, analyser_connecteurs, penalite_quota,
    score_syntaxe, score_orthographe, _fautes_fallback
)
from aziza.machine_etats import ProfilApprenant, MachineEtats


# ═══════════════════════════════════════════════════════════════════════════════
# SIMILARITÉ
# ═══════════════════════════════════════════════════════════════════════════════

class TestTokenize(unittest.TestCase):

    def test_tokenize_basic(self):
        self.assertEqual(tokenize("Le Benin est un pays"), ["le", "benin", "est", "un", "pays"])

    def test_tokenize_empty(self):
        self.assertEqual(tokenize(""), [])

    def test_tokenize_accented(self):
        t = tokenize("À l'école, ça commence dès l'enfance")
        self.assertIn("école", t)
        self.assertIn("commence", t)
        self.assertIn("enfance", t)

    def test_tokenize_punctuation_only(self):
        self.assertEqual(tokenize("?!,;:..."), [])

    def test_tokenize_mixed_case(self):
        t = tokenize("BENIN Est un PAYS")
        self.assertEqual(t, ["benin", "est", "un", "pays"])


class TestNgrams(unittest.TestCase):

    def test_ngrams_basic(self):
        self.assertEqual(ngrams(["a", "b", "c"], 2), [("a", "b"), ("b", "c")])

    def test_ngrams_too_short(self):
        self.assertEqual(ngrams(["a"], 2), [])

    def test_ngrams_empty(self):
        self.assertEqual(ngrams([], 2), [])

    def test_ngrams_exact(self):
        self.assertEqual(ngrams(["a", "b"], 2), [("a", "b")])

    def test_ngrams_n3(self):
        self.assertEqual(ngrams(["a", "b", "c", "d"], 3), [("a", "b", "c"), ("b", "c", "d")])


class TestAnalyserSimilarite(unittest.TestCase):

    def test_structure_retour(self):
        r = analyser_similarite("Le Benin est un pays.", "Le Benin est un pays.")
        for key in ["score_lcs", "score_jaccard", "score_tfidf", "score_plagiat",
                     "label_plagiat", "seuil_lcs", "seuil_plagiat", "smin"]:
            self.assertIn(key, r)

    def test_plagiat_detecte(self):
        r = analyser_similarite("Texte identique mot pour mot.", "Texte identique mot pour mot.")
        self.assertEqual(r["label_plagiat"], "plagiat")

    def test_original_label(self):
        r = analyser_similarite("Un texte sur le climat en Afrique.",
                                "Un tout autre sujet sans rapport.")
        self.assertEqual(r["label_plagiat"], "original")


class TestSimilarite(unittest.TestCase):

    def test_lcs_identical(self):
        self.assertEqual(lcs_score("abcde", "abcde"), 1.0)

    def test_lcs_empty(self):
        self.assertEqual(lcs_score("abc", ""), 0.0)
        self.assertEqual(lcs_score("", "abc"), 0.0)
        self.assertEqual(lcs_score("", ""), 0.0)

    def test_lcs_partial(self):
        s = lcs_score("Le Benin est un pays", "Le Benin est un paie")
        self.assertGreater(s, 0.5)
        self.assertLess(s, 1.0)

    def test_lcs_no_common(self):
        self.assertEqual(lcs_score("abc", "xyz"), 0.0)

    def test_lcs_different_case(self):
        s = lcs_score("Le Benin", "le benin")
        self.assertAlmostEqual(s, 1.0)

    def test_lcs_repeated_words(self):
        s = lcs_score("le le le le", "le le")
        self.assertEqual(s, 1.0)

    def test_lcs_longer_contraction(self):
        s = lcs_score("une source", "Texte avec une source et beaucoup plus long")
        self.assertGreater(s, 0.0)
        self.assertLessEqual(s, 1.0)

    def test_parabole_plagiat(self):
        self.assertEqual(score_plagiat_parabole(0.80), 0.0)
        self.assertEqual(score_plagiat_parabole(0.90), 0.0)

    def test_parabole_hors_sujet(self):
        self.assertEqual(score_plagiat_parabole(0.0), 0.0)
        self.assertEqual(score_plagiat_parabole(SMIN - 0.01), 0.0)

    def test_parabole_peak(self):
        mid = (SMIN + SEUIL_PLAGIAT) / 2
        s = score_plagiat_parabole(mid)
        self.assertGreater(s, 1.0)
        self.assertLessEqual(s, 2.0)

    def test_parabole_near_smin(self):
        s = score_plagiat_parabole(SMIN + 0.01)
        self.assertGreater(s, 0.0)
        self.assertLess(s, 2.0)

    def test_parabole_near_seuil(self):
        s = score_plagiat_parabole(SEUIL_PLAGIAT - 0.01)
        self.assertGreater(s, 0.0)
        self.assertLess(s, 2.0)

    def test_parabole_step_size(self):
        s1 = score_plagiat_parabole(0.50)
        s2 = score_plagiat_parabole(0.51)
        self.assertAlmostEqual(abs(s1 - s2) * 4, round(abs(s1 - s2) * 4))  # pas de 0.25

    def test_label_original(self):
        self.assertEqual(label_plagiat(0.0), "original")
        self.assertEqual(label_plagiat(0.3), "original")

    def test_label_similaire(self):
        self.assertEqual(label_plagiat(0.70), "similaire")

    def test_label_plagiat(self):
        self.assertEqual(label_plagiat(0.80), "plagiat")
        self.assertEqual(label_plagiat(0.95), "plagiat")

    def test_jaccard_identical(self):
        self.assertAlmostEqual(jaccard_bigrams("abc def", "abc def"), 1.0)

    def test_jaccard_empty(self):
        self.assertEqual(jaccard_bigrams("", "abc"), 0.0)
        self.assertEqual(jaccard_bigrams("abc", ""), 0.0)

    def test_jaccard_partial(self):
        s = jaccard_bigrams("le benin est un pays", "le benin est un grand pays")
        self.assertGreater(s, 0.0)
        self.assertLess(s, 1.0)

    def test_jaccard_no_match(self):
        self.assertEqual(jaccard_bigrams("abc def", "xyz wxy"), 0.0)

    def test_jaccard_symmetry(self):
        s1 = jaccard_bigrams("le benin est un pays", "le benin est")
        s2 = jaccard_bigrams("le benin est", "le benin est un pays")
        self.assertEqual(s1, s2)

    def test_cosinus_tfidf_basic(self):
        s = cosinus_tfidf("Le Benin est un pays", "Le Benin est un pays")
        self.assertGreater(s, 0.9)

    def test_cosinus_tfidf_empty(self):
        s = cosinus_tfidf("abc", "")
        self.assertAlmostEqual(s, 0.0)

    def test_cosinus_tfidf_partial(self):
        s = cosinus_tfidf("Le Benin est un pays d Afrique",
                          "Le Benin est un pays")
        self.assertGreater(s, 0.0)
        self.assertLess(s, 1.0)

    def test_cosinus_tfidf_no_match(self):
        s = cosinus_tfidf("abc def", "xyz wxy")
        self.assertAlmostEqual(s, 0.0)


# ═══════════════════════════════════════════════════════════════════════════════
# FORME
# ═══════════════════════════════════════════════════════════════════════════════

class TestForme(unittest.TestCase):

    def test_compter_phrases_base(self):
        self.assertEqual(compter_phrases("Phrase une. Phrase deux!"), 2)
        self.assertEqual(compter_phrases("Phrase unique"), 1)

    def test_compter_phrases_vide(self):
        self.assertEqual(compter_phrases(""), 1)

    def test_compter_phrases_mixed(self):
        self.assertEqual(compter_phrases("A. B? C! D."), 4)

    def test_compter_phrases_trailing(self):
        self.assertEqual(compter_phrases("Phrase. "), 1)

    def test_connecteurs_vide(self):
        r = analyser_connecteurs("")
        self.assertEqual(r["conn_total"], 0)
        self.assertEqual(r["conn_categories"], 0)

    def test_connecteurs_presents(self):
        r = analyser_connecteurs("Premièrement, je pense donc que...")
        self.assertGreaterEqual(r["conn_total"], 1)
        self.assertGreaterEqual(r["conn_categories"], 1)

    def test_connecteurs_multiple_categories(self):
        r = analyser_connecteurs("Premièrement, je pense donc car par exemple")
        self.assertGreaterEqual(r["conn_categories"], 3)

    def test_connecteurs_no_connectors(self):
        r = analyser_connecteurs("Le soleil brille dans le ciel bleu.")
        self.assertEqual(r["conn_total"], 0)
        self.assertEqual(r["conn_categories"], 0)

    def test_connecteurs_details_present(self):
        r = analyser_connecteurs("donc")
        self.assertIn("conn_details", r)
        self.assertGreater(r["conn_details"].get("consequence", 0), 0)

    def test_penalite_continue(self):
        self.assertEqual(penalite_quota(0), 0.0)
        self.assertEqual(penalite_quota(10), 0.2)
        self.assertEqual(penalite_quota(50), 1.0)
        self.assertEqual(penalite_quota(100), 2.0)

    def test_penalite_quota_zero(self):
        self.assertEqual(penalite_quota(0.0), 0.0)

    def test_penalite_quota_max(self):
        self.assertEqual(penalite_quota(150), 2.0)
        self.assertEqual(penalite_quota(999), 2.0)

    def test_score_syntaxe_zero(self):
        self.assertEqual(score_syntaxe(0.0, 0, 0), 0.0)
        self.assertEqual(score_syntaxe(1.0, 1, 1), 0.0)

    def test_score_syntaxe_max(self):
        self.assertGreaterEqual(score_syntaxe(0.25, 10, 4), 1.0)

    def test_score_syntaxe_partial(self):
        self.assertGreater(score_syntaxe(0.3, 5, 2), 0.0)
        self.assertLess(score_syntaxe(0.3, 5, 2), 2.0)

    def test_score_syntaxe_mid_conn_high_cat(self):
        s = score_syntaxe(0.3, 3, 3)
        self.assertGreaterEqual(s, 0.75)

    def test_score_syntaxe_ratio_bounds(self):
        s = score_syntaxe(0.10, 10, 4)
        self.assertEqual(s, 1.0)
        s = score_syntaxe(0.50, 10, 4)
        self.assertEqual(s, 1.0)

    def test_score_orthographe_bareme(self):
        self.assertEqual(score_orthographe(0), 2.0)
        self.assertEqual(score_orthographe(1), 1.5)
        self.assertEqual(score_orthographe(3), 1.0)
        self.assertEqual(score_orthographe(5), 0.25)
        self.assertEqual(score_orthographe(6), 0.0)

    def test_fautes_fallback_basic(self):
        r = _fautes_fallback("J'ai fait une ereur")
        self.assertGreaterEqual(r["nb"], 1)
        self.assertGreaterEqual(len(r["details"]), 1)
        self.assertIn("message", r["details"][0])

    def test_fautes_fallback_no_fault(self):
        r = _fautes_fallback("Ce texte est correctement ecrit.")
        self.assertEqual(r["nb"], 0)
        self.assertEqual(r["details"], [])

    def test_fautes_fallback_multiple(self):
        r = _fautes_fallback("J'ai fait une ereur et une fote")
        self.assertGreaterEqual(r["nb"], 2)

    def test_evaluer_forme_contraction_courte(self):
        from aziza.pipeline.forme import evaluer_forme
        r = evaluer_forme("Texte source de plusieurs mots.", "Texte", 30, 3)
        self.assertIn("score_lexical", r)
        self.assertIn("score_syntaxe", r)
        self.assertIn("score_orthographe", r)
        self.assertIn("fautes_details", r)
        self.assertIn("label_plagiat", r)

    def test_evaluer_forme_identique(self):
        from aziza.pipeline.forme import evaluer_forme
        txt = "Le Benin est un pays situe en Afrique."
        r = evaluer_forme(txt, txt, 10, 10)
        self.assertEqual(r["label_plagiat"], "plagiat")

    def test_evaluer_forme_normal(self):
        from aziza.pipeline.forme import evaluer_forme
        src = "Le Benin est un pays situe en Afrique de l Ouest. Sa capitale est Porto Novo."
        ctr = "Le Benin se trouve en Afrique de l Ouest. Porto Novo en est la capitale."
        r = evaluer_forme(src, ctr, 20, 18)
        self.assertGreaterEqual(r["score_total"], 0.0)
        self.assertLessEqual(r["score_total"], 7.0)
        self.assertIn("score_lexical", r)
        self.assertIn("score_syntaxe", r)
        self.assertIn("score_orthographe", r)

    def test_evaluer_forme_short_text_ortho_plafond(self):
        from aziza.pipeline.forme import evaluer_forme
        r = evaluer_forme("Texte source ici.", "Hi", 10, 2)
        self.assertLessEqual(r["score_orthographe"], 2.0 * 2/30)

    def test_evaluer_forme_quota_penalty(self):
        from aziza.pipeline.forme import evaluer_forme
        r = evaluer_forme("Texte source avec plusieurs mots pour le test du quota.",
                          "Texte beaucoup trop long par rapport au quota fixe.", 10, 20)
        self.assertGreater(r["penalite_quota"], 0.0)

    def test_evaluer_forme_keys(self):
        from aziza.pipeline.forme import evaluer_forme
        r = evaluer_forme("Texte source.", "Contraction.", 10, 4)
        expected = ["score_lexical", "score_syntaxe", "score_orthographe",
                     "score_plagiat", "label_plagiat", "score_lcs",
                     "penalite_quota", "ecart_pct", "nb_fautes",
                     "fautes_details", "connecteurs_total", "connecteurs_cat",
                     "ratio_phrases", "score_total"]
        for k in expected:
            self.assertIn(k, r)


# ═══════════════════════════════════════════════════════════════════════════════
# MACHINE À ÉTATS
# ═══════════════════════════════════════════════════════════════════════════════

class TestMachineEtats(unittest.TestCase):

    def test_profil_creation(self):
        p = ProfilApprenant("Test")
        self.assertEqual(p.nom, "Test")
        self.assertEqual(p.palier_actuel, "decouverte")

    def test_score_moyen(self):
        p = ProfilApprenant("Test", scores=[8, 7, 9], nb_exercices=3)
        self.assertAlmostEqual(p.score_moyen_exercices(), 80.0)

    def test_score_moyen_empty(self):
        p = ProfilApprenant("Test")
        self.assertEqual(p.score_moyen_exercices(), 0.0)

    def test_score_moyen_single(self):
        p = ProfilApprenant("Test", scores=[6], nb_exercices=1)
        self.assertAlmostEqual(p.score_moyen_exercices(), 60.0)

    def test_score_moyen_last_three_only(self):
        p = ProfilApprenant("Test", scores=[1, 2, 3, 8, 9, 10], nb_exercices=6)
        self.assertAlmostEqual(p.score_moyen_exercices(), 90.0)

    def test_to_dict(self):
        p = ProfilApprenant("Test", scores=[8, 7, 9], nb_exercices=3,
                            nb_tests=1, historique_mp=[75.0])
        d = p.to_dict()
        self.assertEqual(d["nom"], "Test")
        self.assertEqual(d["palier_actuel"], "decouverte")
        self.assertEqual(d["nb_exercices"], 3)
        self.assertEqual(d["nb_tests"], 1)
        self.assertAlmostEqual(d["score_moyen"], 80.0)

    def test_enregistrer_exercice(self):
        p = ProfilApprenant("Test")
        m = MachineEtats(p)
        m.enregistrer_exercice(7.5)
        self.assertEqual(p.nb_exercices, 1)
        self.assertEqual(p.scores, [7.5])

    def test_enregistrer_exercice_invalide(self):
        p = ProfilApprenant("Test")
        m = MachineEtats(p)
        with self.assertRaises(ValueError):
            m.enregistrer_exercice(11)
        with self.assertRaises(ValueError):
            m.enregistrer_exercice(-1)

    def test_calculer_mp(self):
        p = ProfilApprenant("Test", scores=[7, 8, 6], nb_exercices=3)
        m = MachineEtats(p)
        self.assertAlmostEqual(m.calculer_mp(7.0), 70.0)

    def test_calculer_mp_no_exercises(self):
        p = ProfilApprenant("Test", scores=[], nb_exercices=0)
        m = MachineEtats(p)
        self.assertAlmostEqual(m.calculer_mp(7.0), 42.0)

    def test_evaluer_cycle_progression(self):
        p = ProfilApprenant("Test", scores=[8, 9, 7], nb_exercices=3)
        m = MachineEtats(p)
        r = m.evaluer_cycle(8.0)
        self.assertEqual(r["decision"], "progression")

    def test_evaluer_cycle_statu_quo(self):
        p = ProfilApprenant("Test", scores=[7, 6, 8], nb_exercices=3)
        m = MachineEtats(p)
        r = m.evaluer_cycle(7.0)
        self.assertEqual(r["decision"], "statu_quo")

    def test_evaluer_cycle_consolidation(self):
        p = ProfilApprenant("Test", scores=[4, 5, 3], nb_exercices=3)
        m = MachineEtats(p)
        r = m.evaluer_cycle(5.0)
        self.assertEqual(r["decision"], "consolidation")

    def test_evaluer_cycle_palier_progression(self):
        p = ProfilApprenant("Test", scores=[9, 8, 9], nb_exercices=3,
                            palier_actuel="decouverte")
        m = MachineEtats(p)
        r = m.evaluer_cycle(8.0)
        self.assertEqual(r["decision"], "progression")
        self.assertEqual(r["palier_apres"], "consolidation")

    def test_evaluer_cycle_palier_maitrise(self):
        p = ProfilApprenant("Test", scores=[9, 8, 9], nb_exercices=3,
                            palier_actuel="consolidation")
        m = MachineEtats(p)
        r = m.evaluer_cycle(9.0)
        self.assertEqual(r["palier_apres"], "maitrise")

    def test_evaluer_cycle_incremente_nb_tests(self):
        p = ProfilApprenant("Test", scores=[7, 8, 6], nb_exercices=3)
        m = MachineEtats(p)
        m.evaluer_cycle(7.0)
        self.assertEqual(p.nb_tests, 1)
        m.evaluer_cycle(7.0)
        self.assertEqual(p.nb_tests, 2)

    def test_statut(self):
        p = ProfilApprenant("Test", scores=[7, 8], nb_exercices=2)
        m = MachineEtats(p)
        s = m.statut()
        self.assertIn("palier_suivant", s)
        self.assertIn("historique_mp", s)
        self.assertIn("seuil_progression", s)

    def test_cycle_invalide(self):
        p = ProfilApprenant("Test")
        m = MachineEtats(p)
        with self.assertRaises(ValueError):
            m.evaluer_cycle(11)

    def test_historique_mp_append(self):
        p = ProfilApprenant("Test", scores=[7, 8, 6], nb_exercices=3)
        m = MachineEtats(p)
        m.evaluer_cycle(7.0)
        self.assertEqual(len(p.historique_mp), 1)
        m.evaluer_cycle(8.0)
        self.assertEqual(len(p.historique_mp), 2)


# ═══════════════════════════════════════════════════════════════════════════════
# FOND (sans API)
# ═══════════════════════════════════════════════════════════════════════════════

class TestCleanJson(unittest.TestCase):

    def setUp(self):
        from aziza.pipeline.fond import _clean_json_response
        self.fn = _clean_json_response

    def test_valid_json(self):
        r = self.fn('{"score_fond": 2.5, "contresens_detecte": false}')
        self.assertEqual(r["score_fond"], 2.5)
        self.assertFalse(r["contresens_detecte"])

    def test_valid_json_with_subjectivite(self):
        r = self.fn('{"score_fond": 2, "subjectivite_detectee": true, "phrase_subjective": "A mon avis"}')
        self.assertTrue(r["subjectivite_detectee"])
        self.assertEqual(r["phrase_subjective"], "A mon avis")

    def test_malformed_json_regex_fallback(self):
        raw = '{"score_fond": 1.5, "contresens_detecte": true, garbage}'
        r = self.fn(raw)
        self.assertEqual(r["score_fond"], 1.5)
        self.assertTrue(r["contresens_detecte"])

    def test_malformed_with_idees(self):
        raw = '{"score_fond": 2, "idees_manquantes": ["idee1", "idee2"], broken}'
        r = self.fn(raw)
        self.assertEqual(r["score_fond"], 2.0)
        self.assertIn("idee1", r["idees_manquantes"])

    def test_empty_string(self):
        r = self.fn("")
        self.assertEqual(r["score_fond"], 1.5)
        self.assertFalse(r["contresens_detecte"])

    def test_no_score_found(self):
        r = self.fn('{broken json, no score here')
        self.assertEqual(r["score_fond"], 1.5)

    def test_markdown_wrapped(self):
        r = self.fn('```json\n{"score_fond": 3.0}\n```')
        self.assertEqual(r["score_fond"], 3.0)

    def test_feedback_fields(self):
        raw = '{"raisonnement": "Bon texte.", "feedback_erreur": "Aucune erreur."}'
        r = self.fn(raw)
        self.assertIn("Bon texte.", r["raisonnement"])
        self.assertIn("Aucune erreur.", r["feedback_erreur"])


class TestCalibrer(unittest.TestCase):

    def setUp(self):
        from aziza.pipeline.fond import _calibrer
        self.fn = _calibrer

    def test_normal_no_adjustment(self):
        score, contresens = self.fn(2.5, False, 0.92)
        self.assertEqual(score, 2.5)
        self.assertFalse(contresens)

    def test_sem_low_high_llm(self):
        score, contresens = self.fn(3.0, False, 0.88)
        self.assertLess(score, 3.0)
        self.assertGreaterEqual(score, 1.0)

    def test_sem_very_low(self):
        score, contresens = self.fn(2.0, False, 0.80)
        self.assertTrue(contresens)
        self.assertLessEqual(score, 1.0)

    def test_subjectivite_penalty(self):
        score, contresens = self.fn(3.0, False, 0.95, subjectivite=True)
        self.assertEqual(score, 2.0)

    def test_subjectivite_avec_sem_low(self):
        score, contresens = self.fn(2.0, False, 0.88, subjectivite=True)
        self.assertLessEqual(score, 1.0)

    def test_subjectivite_at_zero(self):
        score, contresens = self.fn(0.0, False, 0.95, subjectivite=True)
        self.assertEqual(score, 0.0)

    def test_sem_just_above_threshold(self):
        score, contresens = self.fn(2.5, False, 0.90)
        self.assertAlmostEqual(score, 2.5)
        self.assertFalse(contresens)

    def test_sem_exactly_at_threshold(self):
        score, contresens = self.fn(2.5, False, 0.85)
        self.assertEqual(score, 2.0)
        self.assertFalse(contresens)


# ═══════════════════════════════════════════════════════════════════════════════
# COMPLET (avec mock)
# ═══════════════════════════════════════════════════════════════════════════════

class TestCompletMock(unittest.TestCase):

    def _mock_fond(self, score_sem=0.95, score_fond_brut=2.5, contresens=False,
                   subjectivite=False):
        return {
            "score_fond_brut": score_fond_brut,
            "score_fond_calibre": score_fond_brut,
            "contresens_detecte": contresens,
            "subjectivite_detectee": subjectivite,
            "phrase_subjective": "",
            "idees_manquantes": [],
            "score_semantique": score_sem,
            "raisonnement": "",
            "feedback_erreur": "",
            "feedback_micro_cours": "",
            "feedback_exemple": "",
        }

    def _mock_ortho(self, *args, **kwargs):
        return {"nb": 0, "details": []}

    @patch("aziza.pipeline.complet.evaluer_fond")
    @patch("aziza.pipeline.forme._fautes_languagetool")
    def test_normal_evaluation(self, mock_ortho, mock_fond):
        mock_fond.return_value = self._mock_fond(0.95, 2.5)
        mock_ortho.side_effect = self._mock_ortho
        from aziza.pipeline.complet import evaluer_complet
        r = evaluer_complet(
            "Le Benin est un pays situe en Afrique de l Ouest. Sa capitale est Porto Novo.",
            "Le Benin est un pays de l Afrique de l Ouest dont la capitale est Porto Novo.",
            20, 24
        )
        self.assertFalse(r["verrou_plagiat"])
        self.assertFalse(r["verrou_hors_sujet"])
        self.assertFalse(r["verrou_trop_court"])
        self.assertGreater(r["note_finale"], 0.0)
        self.assertLessEqual(r["note_finale"], 10.0)

    @patch("aziza.pipeline.complet.evaluer_fond")
    @patch("aziza.pipeline.forme._fautes_languagetool")
    def test_verrou_plagiat(self, mock_ortho, mock_fond):
        mock_fond.return_value = self._mock_fond(0.95, 2.5)
        mock_ortho.side_effect = self._mock_ortho
        from aziza.pipeline.complet import evaluer_complet
        src = "Texte identique mot pour mot dans les deux."
        r = evaluer_complet(src, src, 10, 10)
        self.assertTrue(r["verrou_plagiat"])
        self.assertEqual(r["note_finale"], 0.0)

    @patch("aziza.pipeline.complet.evaluer_fond")
    @patch("aziza.pipeline.forme._fautes_languagetool")
    def test_verrou_trop_court(self, mock_ortho, mock_fond):
        mock_fond.return_value = self._mock_fond(0.95, 2.5)
        mock_ortho.side_effect = self._mock_ortho
        from aziza.pipeline.complet import evaluer_complet
        r = evaluer_complet("Long texte source pour le test.", "Trop court", 20, 2)
        self.assertTrue(r["verrou_trop_court"])
        self.assertEqual(r["note_finale"], 0.0)

    @patch("aziza.pipeline.complet.evaluer_fond")
    @patch("aziza.pipeline.forme._fautes_languagetool")
    def test_verrou_hors_sujet(self, mock_ortho, mock_fond):
        mock_fond.return_value = self._mock_fond(0.70, 0.5, contresens=True)
        mock_ortho.side_effect = self._mock_ortho
        from aziza.pipeline.complet import evaluer_complet
        r = evaluer_complet("Texte sur le climat en Afrique.",
                            "Sujet totalement different.", 20, 10)
        self.assertTrue(r["verrou_hors_sujet"])
        self.assertEqual(r["score_fond"], 0.0)

    @patch("aziza.pipeline.complet.evaluer_fond")
    @patch("aziza.pipeline.forme._fautes_languagetool")
    def test_note_finale_range(self, mock_ortho, mock_fond):
        mock_fond.return_value = self._mock_fond(0.95, 2.5)
        mock_ortho.side_effect = self._mock_ortho
        from aziza.pipeline.complet import evaluer_complet
        r = evaluer_complet("Le Benin est un pays d Afrique.",
                            "Le Benin est un pays d Afrique de l Ouest.", 20, 20)
        self.assertGreaterEqual(r["note_finale"], 0.0)
        self.assertLessEqual(r["note_finale"], 10.0)

    @patch("aziza.pipeline.complet.evaluer_fond")
    @patch("aziza.pipeline.forme._fautes_languagetool")
    def test_verrous_exclusifs(self, mock_ortho, mock_fond):
        mock_fond.return_value = self._mock_fond(0.70, 0.5, contresens=True)
        mock_ortho.side_effect = self._mock_ortho
        from aziza.pipeline.complet import evaluer_complet
        r = evaluer_complet("Texte source.", "texte source.", 10, 8)
        trop_court = r["verrou_trop_court"]
        hors_sujet = r["verrou_hors_sujet"]
        plagiat = r["verrou_plagiat"]
        verrous_actifs = sum([trop_court, hors_sujet, plagiat])
        self.assertGreaterEqual(verrous_actifs, 1)

    @patch("aziza.pipeline.complet.evaluer_fond")
    @patch("aziza.pipeline.forme._fautes_languagetool")
    def test_structure_retour_complete(self, mock_ortho, mock_fond):
        mock_fond.return_value = self._mock_fond(0.95, 2.5)
        mock_ortho.side_effect = self._mock_ortho
        from aziza.pipeline.complet import evaluer_complet
        r = evaluer_complet("Le Benin est un pays.", "Le Benin est un pays.", 10, 20)
        expected = [
            "score_lexical", "score_syntaxe", "score_orthographe",
            "score_plagiat", "label_plagiat", "score_lcs",
            "penalite_quota", "ecart_pct", "nb_fautes", "fautes_details",
            "connecteurs_total", "connecteurs_cat", "ratio_phrases",
            "score_fond_brut", "score_fond_calibre", "contresens_detecte",
            "subjectivite_detectee", "phrase_subjective", "idees_manquantes",
            "score_semantique", "raisonnement", "feedback_erreur",
            "feedback_micro_cours", "feedback_exemple",
            "verrou_plagiat", "verrou_hors_sujet", "verrou_trop_court",
            "score_forme", "score_fond", "note_finale",
        ]
        for k in expected:
            self.assertIn(k, r)


# ═══════════════════════════════════════════════════════════════════════════════
# INTÉGRATION LENTE (API Mistral)
# ═══════════════════════════════════════════════════════════════════════════════

SLOW_TESTS = len(sys.argv) > 1 and sys.argv[1] == "all"

class TestCompletIntegration(unittest.TestCase):

    def setUp(self):
        self.src = (
            "Le Benin est un pays situe en Afrique de l Ouest. "
            "Sa capitale est Porto-Novo. La langue officielle est le francais."
        )

    def test_structure_retour(self):
        if not SLOW_TESTS:
            self.skipTest("Passer --all pour les tests API")
        from aziza.pipeline.complet import evaluer_complet
        r = evaluer_complet(self.src, "Le Benin est un pays.", 40, 6)
        for key in ["score_lexical", "score_forme", "score_fond", "note_finale",
                     "verrou_plagiat", "verrou_hors_sujet", "verrou_trop_court",
                     "fautes_details", "label_plagiat", "subjectivite_detectee"]:
            self.assertIn(key, r)

    def test_verrou_plagiat(self):
        if not SLOW_TESTS:
            self.skipTest("Passer --all pour les tests API")
        from aziza.pipeline.complet import evaluer_complet
        r = evaluer_complet(self.src, self.src, 40, 40)
        self.assertTrue(r["verrou_plagiat"])
        self.assertEqual(r["note_finale"], 0.0)

    def test_verrou_trop_court(self):
        if not SLOW_TESTS:
            self.skipTest("Passer --all pour les tests API")
        from aziza.pipeline.complet import evaluer_complet
        r = evaluer_complet(self.src, "Trop court", 40, 2)
        self.assertTrue(r["verrou_trop_court"])
        self.assertEqual(r["note_finale"], 0.0)


# ═══════════════════════════════════════════════════════════════════════════════
# LANCEMENT
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)


# python tests.py all
