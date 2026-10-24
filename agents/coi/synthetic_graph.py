"""Seed a named synthetic document without deleting unrelated graph data."""
from .graph_manager import get_graph, close_graph

COMPANIES = [
    "Alpha Corp",
    "Beta Technologies",
    "Gamma Holdings",
    "Delta Solutions",
    "Epsilon Ventures",
    "Zeta Industries",
    "Eta Partners",
    "Theta Capital",
    "Iota Systems",
    "Kappa Group",
]

VENDORS = [
    "Vendor One Ltd",
    "Vendor Two Inc",
    "Vendor Three LLC",
    "Vendor Four GmbH",
    "Vendor Five Co",
]

LAW_FIRMS = [
    "LawFirm Alpha & Associates",
    "LawFirm Beta Partners LLP",
    "LawFirm Gamma Solicitors",
]

# (from_entity, to_entity, relationship_type)
RELATIONSHIPS = [
    # Corporate structure
    ("Beta Technologies",    "Gamma Holdings",   "SUBSIDIARY_OF"),
    ("Delta Solutions",      "Gamma Holdings",   "SUBSIDIARY_OF"),
    ("Epsilon Ventures",     "Kappa Group",      "SUBSIDIARY_OF"),
    ("Vendor One Ltd",       "Gamma Holdings",   "AFFILIATED_WITH"),
    ("Vendor Two Inc",       "Kappa Group",      "AFFILIATED_WITH"),

    # Litigation  ← adversarial, triggers HIGH severity
    ("Gamma Holdings",       "Alpha Corp",       "LITIGATING_AGAINST"),
    ("Iota Systems",         "Eta Partners",     "LITIGATING_AGAINST"),

    # Competition  ← MEDIUM severity
    ("Delta Solutions",      "Alpha Corp",       "COMPETES_WITH"),
    ("Zeta Industries",      "Theta Capital",    "COMPETES_WITH"),

    # Legal representation
    ("LawFirm Alpha & Associates", "Alpha Corp",        "REPRESENTS"),
    ("LawFirm Alpha & Associates", "Gamma Holdings",    "REPRESENTS"),  # same firm
    ("LawFirm Beta Partners LLP",  "Beta Technologies", "REPRESENTS"),
    ("LawFirm Gamma Solicitors",   "Iota Systems",      "REPRESENTS"),

    # Contract relationships (neutral – needed for traversal)
    ("Alpha Corp",       "Vendor One Ltd",  "CONTRACT_WITH"),
    ("Beta Technologies","Vendor Three LLC", "CONTRACT_WITH"),
    ("Theta Capital",    "Vendor Four GmbH", "CONTRACT_WITH"),

    # Board member / director overlap  ← LOW severity
    ("Kappa Group",  "Alpha Corp",    "SHARED_DIRECTOR"),

    # Partner chains
    ("Vendor Five Co", "Eta Partners", "PARTNER_OF"),
]


def seed(*, graph=None, doc_id="COI_SYNTHETIC_DEMO"):
    graph = graph or get_graph()
    graph.setup_schema()
    entities = [{"name": n, "label": "Company"} for n in COMPANIES + VENDORS + LAW_FIRMS]
    clause = {"clause_id": "synthetic", "text": "Synthetic test facts. Not legal evidence.",
              "entities": entities, "relationships": [
                  {"from": a, "to": b, "type": t, "verified": False,
                   "evidence": "Synthetic test fixture"} for a, b, t in RELATIONSHIPS]}
    return graph.replace_document({"id": doc_id, "type": "synthetic", "filename": "synthetic_graph.py"}, [clause])


if __name__ == "__main__":
    try:
        print(seed())
    finally:
        close_graph()
