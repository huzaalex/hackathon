"""Legal parameters used by the allocation engine.

!! SIMPLIFIED MODEL FOR THE DEMO - TO BE VERIFIED AGAINST THE OFFICIAL TEXT OF THE LAW !!
Every value here is kept in one place so the team member doing the legal research
can adjust it without touching the algorithm.
"""

from decimal import Decimal

# Credit sources that can never be garnished (fully protected).
EXEMPT_SOURCES = {
    "CHILD_ALLOWANCE": "State child allowance",
    "SOCIAL_BENEFIT": "Social assistance benefit",
    "CHILDCARE_BENEFIT": "Childcare (parental leave) benefit",
}

# Periodic income sources: only a fraction can be garnished, depending on the claim type.
INCOME_SOURCES = {
    "SALARY": "Salary",
    "PENSION": "Pension",
}

# rank: order of preference between creditors (lower = paid first)
# income_fraction: maximum share of periodic income (salary/pension) that may be garnished
CLAIM_TYPES = {
    "WAGE": {
        "label": "Wage claims",
        "rank": 2,
        "income_fraction": Decimal(1) / Decimal(3),
        "legal_basis": "Code of Civil Procedure art. 867(1) item 2 (rank); art. 729 (1/3 limit)",
    },
    "CHILD_SUPPORT": {
        "label": "Child support / maintenance",
        "rank": 3,
        "income_fraction": Decimal(1) / Decimal(2),
        "legal_basis": "Code of Civil Procedure art. 867(1) item 3 (rank); art. 729(2) (1/2 limit)",
    },
    "TAX": {
        "label": "Tax claims (ANAF, local taxes)",
        "rank": 4,
        "income_fraction": Decimal(1) / Decimal(3),
        "legal_basis": "Code of Civil Procedure art. 867(1) item 4; Law 207/2015 (Fiscal Procedure Code)",
    },
    "UNSECURED": {
        "label": "Other (unsecured) claims",
        "rank": 8,
        "income_fraction": Decimal(1) / Decimal(3),
        "legal_basis": "Code of Civil Procedure art. 867(1) item 8 (rank); art. 729(2) (1/3 limit)",
    },
}

# Same-rank garnishments are served in the order they were received (FIFO).
SAME_RANK_STRATEGY = "FIFO"

DISCLAIMER = (
    "Simplified model for the demo. Percentages, creditor ranking and exempt amounts must be verified against the "
    "Romanian Code of Civil Procedure (art. 729, 781, 867) and the Fiscal Procedure Code (Law 207/2015)."
)
