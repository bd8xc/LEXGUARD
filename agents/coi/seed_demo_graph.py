"""Seed Neo4j with 50 fictional companies, 50 people, and 200 COI edges."""

from __future__ import annotations

from .graph_manager import LexGraph


DOC_ID = "LEXGUARD-DEMO-SEED"
SYNTHETIC_NOTE = "SYNTHETIC DEMO ONLY; fictional parties and relationship, not a real-world fact."

# Stable names make the demo graph easy to inspect and query from Swagger.
COMPANIES = [
    "Acme Components Pvt. Ltd.",
    "Alpha Orb Technologies Ltd.",
    "Beta Dynamics Pvt. Ltd.",
    "Epsilon Systems Ltd.",
    "Gamma Logistics Pvt. Ltd.",
    "Delta Innovations Ltd.",
    "Asterion Materials Pvt. Ltd.",
    "BluePeak Industrial Systems Ltd.",
    "Cedarline Electronics Pvt. Ltd.",
    "Dawnstar Engineering Ltd.",
    "Evergreen Components Pvt. Ltd.",
    "Farsight Robotics Ltd.",
    "Golden Axis Manufacturing Pvt. Ltd.",
    "Harborlight Networks Ltd.",
    "Ionbridge Energy Pvt. Ltd.",
    "Juniper Cloud Services Ltd.",
    "Keystone Mobility Pvt. Ltd.",
    "Lattice Medical Devices Ltd.",
    "Meridian Packaging Pvt. Ltd.",
    "Northstar Automation Ltd.",
    "Orchid Data Systems Pvt. Ltd.",
    "Pioneer Circuitry Ltd.",
    "Quantum Forge Technologies Pvt. Ltd.",
    "Redwood Instruments Ltd.",
    "Silverline Chemicals Pvt. Ltd.",
    "Tandem Aerospace Ltd.",
    "Umber Security Systems Pvt. Ltd.",
    "Vectorwave Telecom Ltd.",
    "Westhaven Textiles Pvt. Ltd.",
    "Yellowfin Marine Systems Ltd.",
    "Zenith Battery Works Pvt. Ltd.",
    "Amberfield Agriculture Ltd.",
    "Brightforge Construction Pvt. Ltd.",
    "Clearwater Pharma Ltd.",
    "Driftwood Renewables Pvt. Ltd.",
    "Eastgate Software Ltd.",
    "Fairview Diagnostics Pvt. Ltd.",
    "Granite Peak Mining Ltd.",
    "Highland Sensors Pvt. Ltd.",
    "Indigo Rail Systems Ltd.",
    "Jade Harbor Foods Pvt. Ltd.",
    "Kestrel Aviation Ltd.",
    "Longview Semiconductors Pvt. Ltd.",
    "Moonstone Battery Ltd.",
    "Noblepath Payments Pvt. Ltd.",
    "Openfield Waterworks Ltd.",
    "Prairie Wind Energy Pvt. Ltd.",
    "Quarryside Building Materials Ltd.",
    "Riverbend Storage Pvt. Ltd.",
    "Stonebridge Biotech Ltd.",
]

PEOPLE = [
    "Aarav Mehta", "Aditi Rao", "Vikram Shah", "Priya Nair", "Kabir Iyer",
    "Ananya Kapoor", "Rohan Desai", "Meera Menon", "Ishaan Khanna", "Tara Sen",
    "Dev Malhotra", "Nisha Reddy", "Arjun Bhat", "Kavya Joshi", "Neil D'Souza",
    "Sana Qureshi", "Ritwik Bose", "Ira Kulkarni", "Karan Sethi", "Maya Pillai",
    "Aditya Ghosh", "Leela Varma", "Sameer Anand", "Zoya Contractor", "Rahul Oberoi",
    "Sanjay Khurana", "Rhea Banerjee", "Devika Sood", "Manav Bansal", "Ishita Prasad",
    "Nikhil Shetty", "Pooja Chawla", "Kunal Narang", "Simran Gill", "Harish Iqbal",
    "Tanvi Deshmukh", "Rajat Sinha", "Mira Fernandes", "Yash Tandon", "Sonal Arora",
    "Aman Verghese", "Diya Mukherjee", "Varun Bedi", "Ishani Lal", "Parth Menon",
    "Naina Oberoi", "Rishi Puri", "Ayesha Dutta", "Kartik Anand", "Tisha Roy",
]

LEGACY_COMPANIES = [
    "Tandem Aerospace Ltd.", "Umber Security Systems Pvt. Ltd.",
    "Vectorwave Telecom Ltd.", "Westhaven Textiles Pvt. Ltd.",
    "Yellowfin Marine Systems Ltd.", "Zenith Battery Works Pvt. Ltd.",
    "Amberfield Agriculture Ltd.", "Brightforge Construction Pvt. Ltd.",
    "Clearwater Pharma Ltd.", "Driftwood Renewables Pvt. Ltd.",
    "Eastgate Software Ltd.", "Fairview Diagnostics Pvt. Ltd.",
    "Granite Peak Mining Ltd.", "Highland Sensors Pvt. Ltd.",
    "Indigo Rail Systems Ltd.", "Jade Harbor Foods Pvt. Ltd.",
    "Kestrel Aviation Ltd.", "Longview Semiconductors Pvt. Ltd.",
    "Moonstone Battery Ltd.", "Noblepath Payments Pvt. Ltd.",
    "Openfield Waterworks Ltd.", "Prairie Wind Energy Pvt. Ltd.",
    "Quarryside Building Materials Ltd.", "Riverbend Storage Pvt. Ltd.",
    "Stonebridge Biotech Ltd.",
]


def build_demo_seed() -> tuple[dict, list[dict], list[str]]:
    companies, people = list(COMPANIES), list(PEOPLE)
    names = companies + people
    if len(companies) != 50 or len(people) != 50 or len(set(names)) != 100:
        raise RuntimeError("Demo seed must contain exactly 50 unique companies and 50 unique people")

    clauses: list[dict] = []
    labels = {name: "Company" for name in companies} | {name: "Person" for name in people}

    def add_relationship(index: int, source: str, target: str, relation: str, evidence: str) -> None:
        text = f"{SYNTHETIC_NOTE} {evidence}"
        clauses.append({
            "clause_id": f"DEMO-REL-{index:03d}",
            "text": text,
            "entities": [
                {"name": source, "label": labels[source]},
                {"name": target, "label": labels[target]},
            ],
            "relationships": [{
                "from": source,
                "to": target,
                "type": relation,
                "evidence": text,
                # Verified only within this synthetic fixture, not in reality.
                "verified": True,
            }],
        })

    index = 1
    add_relationship(
        index,
        companies[0],
        companies[1],
        "LITIGATING_AGAINST",
        f"{companies[0]} has an illustrative litigation relationship with {companies[1]}.",
    )
    index += 1

    add_relationship(
        index,
        companies[0],
        companies[1],
        "SHARED_DIRECTOR",
        f"{people[0]} is the synthetic shared CEO of {companies[0]} and {companies[1]}.",
    )
    index += 1

    for person, company in zip(people, companies):
        add_relationship(index, person, company, "FOUNDER_OF", f"{person} is a synthetic founder of {company}.")
        index += 1

    # Aarav Mehta leads both companies in the known COI demo pair.
    for i, company in enumerate(companies):
        person = people[0] if i == 1 else people[i]
        add_relationship(index, person, company, "CEO_OF", f"{person} is the synthetic CEO of {company}.")
        index += 1

    for i in range(25):
        person = people[i + 25]
        company = companies[(i + 7) % len(companies)]
        add_relationship(index, person, company, "MANAGER_OF", f"{person} is a synthetic manager of {company}.")
        index += 1

    for i in range(24):
        owner = people[(i + 5) % len(people)]
        add_relationship(index, owner, companies[i], "OWNS", f"{owner} has synthetic demo ownership of {companies[i]}.")
        index += 1

    for left, right in zip(companies[:-1], companies[1:]):
        add_relationship(index, left, right, "SUBSIDIARY_OF", f"{left} is a synthetic subsidiary of {right}.")
        index += 1

    if len(clauses) != 200 or len({name for clause in clauses for name in (e["name"] for e in clause["entities"])}) != 100:
        raise RuntimeError("Demo graph seed must contain 100 entities and exactly 200 relationships")

    document = {"id": DOC_ID, "type": "Synthetic COI demo seed", "filename": "synthetic_demo_seed"}
    return document, clauses, companies


def main() -> None:
    document, clauses, companies = build_demo_seed()
    graph = LexGraph()
    try:
        graph.setup_schema()
        result = graph.replace_document(document, clauses)
        with graph.driver.session(database=graph.database) as session:
            session.run(
                "MATCH (n:COIEntity) WHERE n.name IN $names SET n.label = 'Company'",
                names=companies,
            ).consume()
            session.run(
                "MATCH (n:COIEntity) WHERE n.name IN $names SET n.label = 'Person'",
                names=PEOPLE,
            ).consume()
        # Remove nodes left over from the prior random-name demo seed, but keep
        # any node that another graph document still references.
        with graph.driver.session(database=graph.database) as session:
            session.run(
                "MATCH (n:COIEntity) "
                "WHERE (n.name STARTS WITH 'Fictional Company ' OR n.name STARTS WITH 'Fictional Person ' "
                "OR n.name IN $legacy_names) "
                "AND NOT EXISTS { MATCH (n)-[:EXTRACTED_FROM]->(:COIClause) } "
                "AND NOT EXISTS { MATCH (n)-[:COI_RELATES_TO]-() } "
                "DETACH DELETE n",
                legacy_names=LEGACY_COMPANIES,
            ).consume()
        print(f"Seeded 50 companies, 50 people, and {result['clauses']} synthetic relationships for {DOC_ID}.")
        print("Use this client: " + companies[0])
        print("Use this counterparty: " + companies[1])
        print("All 50 fictional company/person names:")
        for name in companies + PEOPLE:
            print(f"- {name}")
    finally:
        graph.close()


if __name__ == "__main__":
    main()
