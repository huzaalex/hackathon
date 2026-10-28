"""Legal parameters used by the allocation engine.

!! MODEL SIMPLIFICAT PENTRU DEMO - DE VERIFICAT ÎN TEXTUL OFICIAL AL LEGII !!
Every value here is kept in one place so the team member doing the legal research
can adjust it without touching the algorithm.
"""

from decimal import Decimal

# Credit sources that can never be garnished (fully protected).
EXEMPT_SOURCES = {
    "ALOCATIE": "Alocație de stat pentru copii",
    "AJUTOR_SOCIAL": "Ajutor social / prestații de asistență socială",
    "INDEMNIZATIE_CRESTERE_COPIL": "Indemnizație pentru creșterea copilului",
}

# Periodic income sources: only a fraction can be garnished, depending on the claim type.
INCOME_SOURCES = {
    "SALARIU": "Salariu",
    "PENSIE": "Pensie",
}

# rank: order of preference between creditors (lower = paid first)
# income_fraction: maximum share of periodic income (salary/pension) that may be garnished
CLAIM_TYPES = {
    "SALARIALA": {
        "label": "Creanțe salariale",
        "rank": 2,
        "income_fraction": Decimal(1) / Decimal(3),
        "legal_basis": "art. 867 alin. (1) pct. 2 C.proc.civ. (rang); art. 729 C.proc.civ. (limită 1/3)",
    },
    "INTRETINERE": {
        "label": "Obligație de întreținere (pensie alimentară)",
        "rank": 3,
        "income_fraction": Decimal(1) / Decimal(2),
        "legal_basis": "art. 867 alin. (1) pct. 3 C.proc.civ. (rang); art. 729 alin. (2) C.proc.civ. (limită 1/2)",
    },
    "FISCALA": {
        "label": "Creanțe fiscale (ANAF, buget local)",
        "rank": 4,
        "income_fraction": Decimal(1) / Decimal(3),
        "legal_basis": "art. 867 alin. (1) pct. 4 C.proc.civ.; Legea 207/2015 (Cod procedură fiscală)",
    },
    "CHIROGRAFARA": {
        "label": "Alte creanțe (chirografare)",
        "rank": 8,
        "income_fraction": Decimal(1) / Decimal(3),
        "legal_basis": "art. 867 alin. (1) pct. 8 C.proc.civ. (rang); art. 729 alin. (2) C.proc.civ. (limită 1/3)",
    },
}

# Same-rank garnishments are served in the order they were received (FIFO).
SAME_RANK_STRATEGY = "FIFO"

DISCLAIMER = (
    "Model simplificat pentru demo. Procentele, ordinea de preferință și sumele exceptate trebuie verificate "
    "în Codul de procedură civilă (art. 729, 781, 867) și Codul de procedură fiscală (Legea 207/2015)."
)
