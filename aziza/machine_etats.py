"""
aziza/machine_etats.py
=======================
Machine à états gérant la progression adaptative de l'apprenant
dans AZIZA v2.0.

3 paliers de compétence :
    DECOUVERTE   → score < 70%
    CONSOLIDATION → 70% ≤ score < 75%
    MAITRISE     → score ≥ 75%

Algorithme Mₚ :
    Mₚ = 0.4 × moyenne_exercices + 0.6 × note_test
    Mₚ ≥ 75% → progression au palier supérieur
    70% ≤ Mₚ < 75% → statu quo
    Mₚ < 70% → consolidation (pas de régression en v2.0)

Notes : les scores d'exercices et tests sont sur /10 (note globale).
"""

from dataclasses import dataclass, field
from typing import Optional


# ── CONSTANTES ────────────────────────────────────────────────────────────────
PALIER_DECOUVERTE    = "decouverte"
PALIER_CONSOLIDATION = "consolidation"
PALIER_MAITRISE      = "maitrise"

PALIERS_ORDRE = [PALIER_DECOUVERTE, PALIER_CONSOLIDATION, PALIER_MAITRISE]

SEUIL_PROGRESSION   = 75.0   # Mₚ ≥ 75% → palier suivant
SEUIL_STATU_QUO     = 70.0   # 70% ≤ Mₚ < 75% → statu quo
POIDS_EXERCICES     = 0.4
POIDS_TEST          = 0.6
CYCLE_EXERCICES     = 3       # Nombre d'exercices avant le test de niveau


@dataclass
class ProfilApprenant:
    """Représente le profil de compétence d'un apprenant."""

    nom:             str
    palier_actuel:   str   = PALIER_DECOUVERTE
    scores:          list  = field(default_factory=list)
    nb_exercices:    int   = 0
    nb_tests:        int   = 0
    historique_mp:   list  = field(default_factory=list)
    exercices_cycle: int   = 0

    def score_moyen_exercices(self) -> float:
        """Moyenne des 3 derniers scores d'exercices (sur 10, converti en %)."""
        derniers = self.scores[-CYCLE_EXERCICES:]
        if not derniers:
            return 0.0
        return (sum(derniers) / len(derniers)) / 10.0 * 100.0

    def to_dict(self) -> dict:
        return {
            "nom":             self.nom,
            "palier_actuel":   self.palier_actuel,
            "nb_exercices":    self.nb_exercices,
            "nb_tests":        self.nb_tests,
            "score_moyen":     round(self.score_moyen_exercices(), 1),
            "exercices_cycle": self.exercices_cycle,
        }

    @property
    def cycle_complet(self) -> bool:
        return self.exercices_cycle >= CYCLE_EXERCICES


class MachineEtats:
    """
    Machine à états pour la progression adaptative de l'apprenant.

    Usage :
        machine = MachineEtats(ProfilApprenant(nom="Koffi"))
        machine.enregistrer_exercice(score=4)
        machine.enregistrer_exercice(score=3)
        machine.enregistrer_exercice(score=5)
        resultat = machine.evaluer_cycle(note_test=4)
        print(resultat)
    """

    def __init__(self, profil: ProfilApprenant):
        self.profil = profil

    def enregistrer_exercice(self, score: float) -> None:
        """
        Enregistre le score d'un exercice (0-10).
        Incrémente le compteur du cycle en cours.
        """
        if not (0 <= score <= 10):
            raise ValueError(f"Score invalide : {score}. Doit être entre 0 et 10.")
        self.profil.scores.append(score)
        self.profil.nb_exercices += 1
        self.profil.exercices_cycle += 1

    def calculer_mp(self, note_test: float) -> float:
        """
        Calcule la Moyenne Pondérée du cycle.

        Mₚ = 0.4 × moyenne_exercices + 0.6 × note_test
        (note_test sur 10, converti en pourcentage)

        Returns:
            float in [0, 100]
        """
        moy_exercices = self.profil.score_moyen_exercices()
        note_test_pct = (note_test / 10.0) * 100.0
        mp = POIDS_EXERCICES * moy_exercices + POIDS_TEST * note_test_pct
        return round(mp, 2)

    def evaluer_cycle(self, note_test: float) -> dict:
        """
        Évalue un cycle complet (3 exercices + 1 test) et met à jour
        le palier de l'apprenant selon la Moyenne Pondérée Mₚ.

        Args:
            note_test : note du test de niveau (0-10)

        Returns:
            {
                "mp":              float,
                "palier_avant":    str,
                "palier_apres":    str,
                "decision":        str,  # 'progression' | 'statu_quo' | 'consolidation'
                "message":         str,
                "prochaine_difficulte": str,
            }
        """
        if not (0 <= note_test <= 10):
            raise ValueError(f"Note test invalide : {note_test}.")

        self.profil.nb_tests += 1
        self.profil.exercices_cycle = 0
        mp           = self.calculer_mp(note_test)
        palier_avant = self.profil.palier_actuel
        idx_actuel   = PALIERS_ORDRE.index(palier_avant)

        self.profil.historique_mp.append(mp)

        # ── Décision ──────────────────────────────────────────────────────────
        if mp >= SEUIL_PROGRESSION:
            if idx_actuel < len(PALIERS_ORDRE) - 1:
                self.profil.palier_actuel = PALIERS_ORDRE[idx_actuel + 1]
                decision = "progression"
                message  = (
                    f"Félicitations ! Avec une Mₚ de {mp:.1f}%, vous progressez "
                    f"au palier {self.profil.palier_actuel.upper()}. "
                    f"De nouveaux exercices plus avancés vous attendent."
                )
            else:
                decision = "statu_quo"
                message  = (
                    f"Excellent ! Vous avez atteint le niveau MAÎTRISE "
                    f"(Mₚ = {mp:.1f}%). Continuez à pratiquer pour consolider."
                )

        elif mp >= SEUIL_STATU_QUO:
            decision = "statu_quo"
            message  = (
                f"Mₚ = {mp:.1f}% — Vous êtes dans la zone de consolidation. "
                f"Continuez avec des exercices variés sur le même niveau "
                f"avant de tenter une progression."
            )

        else:
            decision = "consolidation"
            message  = (
                f"Mₚ = {mp:.1f}% — Des lacunes persistent. "
                f"AZIZA active le mode consolidation : des exercices "
                f"simplifiés vont vous aider à renforcer les bases."
            )

        # Difficulté du prochain texte proposé
        difficultes = {
            PALIER_DECOUVERTE:    "facile (textes courts, 400-500 mots)",
            PALIER_CONSOLIDATION: "intermédiaire (textes moyens, 500-650 mots)",
            PALIER_MAITRISE:      "difficile (textes longs, 650-750 mots, style complexe)",
        }

        return {
            "mp":                    mp,
            "palier_avant":          palier_avant,
            "palier_apres":          self.profil.palier_actuel,
            "decision":              decision,
            "message":               message,
            "prochaine_difficulte":  difficultes[self.profil.palier_actuel],
        }

    def statut(self) -> dict:
        """Retourne le statut actuel de l'apprenant."""
        idx     = PALIERS_ORDRE.index(self.profil.palier_actuel)
        restant = PALIERS_ORDRE[idx + 1] if idx < len(PALIERS_ORDRE) - 1 else None
        return {
            **self.profil.to_dict(),
            "palier_suivant":    restant,
            "seuil_progression": SEUIL_PROGRESSION,
            "historique_mp":     self.profil.historique_mp,
        }