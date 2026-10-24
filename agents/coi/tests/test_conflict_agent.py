import pytest
from coi.conflict_agent import ConflictOfInterestAgent
from coi.domain import Edge, entity_key
from coi.graph_manager import GraphQueryError, SearchLimitError


class FakeGraph:
    def __init__(self, edges=(), names=(), verified=True):
        self.names = {entity_key(n): n for n in names}
        self.edges = []
        for a, b, kind in edges:
            self.names.update({entity_key(a): a, entity_key(b): b})
            self.edges.append(Edge(source=entity_key(a), target=entity_key(b), type=kind,
                                   doc_id="source", clause_id="clause", evidence="source quote",
                                   verified=verified))

    def resolve_entities(self, names):
        return {k: v for k, v in self.names.items() if k in {entity_key(n) for n in names}}

    def get_neighbors(self, key, *, as_of, limit):
        edges = [e for e in self.edges if key in {e.source, e.target}]
        if len(edges) > limit:
            raise SearchLimitError("neighbor_limit")
        return edges


def run(graph, **limits):
    return ConflictOfInterestAgent(graph=graph, **limits).run(
        client_entity="A", counterparty_entity="B", doc_id="contract")


def test_converging_paths_are_order_independent():
    edges = [("A", "X", "PARTNER_OF"), ("A", "Y", "LITIGATING_AGAINST"),
             ("X", "M", "PARTNER_OF"), ("Y", "M", "PARTNER_OF"), ("M", "B", "PARTNER_OF")]
    reports = [run(FakeGraph(order)) for order in [edges, list(reversed(edges))]]
    assert all(r.severity == "HIGH" for r in reports)
    assert reports[0].findings == reports[1].findings


def test_stronger_path_wins_over_shorter_path():
    report = run(FakeGraph([("A", "B", "SHARED_DIRECTOR"),
                           ("A", "X", "LITIGATING_AGAINST"), ("X", "B", "PARTNER_OF")]))
    assert report.severity == "HIGH"
    assert len(report.findings) == 2
    assert report.findings[0]["evidence"][0]["doc_id"] == "source"


def test_missing_entities_are_unknown():
    report = run(FakeGraph())
    assert report.status == "unknown"
    assert report.conflict_flag is None
    assert report.review_required


def test_case_and_unicode_normalization():
    graph = FakeGraph([("\uff21", "B", "COMPETES_WITH")])
    assert run(graph).severity == "MEDIUM"


def test_known_disconnected_entities_have_no_conflict():
    report = run(FakeGraph(names=["A", "B"]))
    assert report.status == "complete" and report.severity == "NONE"
    assert report.conflict_flag == 0


def test_no_conflict_beyond_three_hops():
    edges = [("A", "X", "LITIGATING_AGAINST"), ("X", "Y", "PARTNER_OF"),
             ("Y", "Z", "PARTNER_OF"), ("Z", "B", "PARTNER_OF")]
    assert not run(FakeGraph(edges)).conflict_detected


@pytest.mark.parametrize("limits", [{"max_expansions": 1}, {"max_neighbors": 1}, {"max_findings": 1}])
def test_limits_never_return_safe(limits):
    graph = FakeGraph([("A", "B", "SHARED_DIRECTOR"), ("A", "X", "LITIGATING_AGAINST"), ("X", "B", "PARTNER_OF")])
    report = run(graph, **limits)
    assert report.status == "incomplete" and report.conflict_flag is None
    assert report.review_required


def test_additional_entities_are_checked_and_bounded():
    graph = FakeGraph([("C", "D", "DISPUTE_WITH")], names=["A", "B"])
    agent = ConflictOfInterestAgent(graph=graph)
    assert agent.run(client_entity="A", counterparty_entity="B", doc_id="D", additional_entities=["C", "D"]).severity == "NONE"
    assert run(graph, max_entities=1).status == "incomplete"


def test_unverified_conflict_is_a_review_lead_not_an_le_flag():
    graph = FakeGraph([("A", "B", "LITIGATING_AGAINST")], verified=False)
    report = run(graph)
    assert report.conflict_detected and report.severity == "HIGH"
    assert report.status == "unknown" and report.conflict_flag is None
    assert report.findings[0]["verified"] is False


def test_unresolved_extra_does_not_hide_verified_party_conflict():
    graph = FakeGraph([("A", "B", "LITIGATING_AGAINST")])
    report = ConflictOfInterestAgent(graph=graph).run(
        client_entity="A", counterparty_entity="B", doc_id="D", additional_entities=["Missing"])
    assert report.conflict_detected and report.severity == "HIGH"
    assert report.status == "incomplete" and report.conflict_flag is None


def test_database_failure_is_not_no_conflict():
    class Broken(FakeGraph):
        def resolve_entities(self, names):
            raise GraphQueryError("offline")
    assert run(Broken()).status == "unavailable"


def test_input_validation():
    with pytest.raises(ValueError):
        ConflictOfInterestAgent(graph=FakeGraph()).run(client_entity=" ", counterparty_entity="B", doc_id="x")
    with pytest.raises(ValueError):
        ConflictOfInterestAgent(graph=FakeGraph()).run(client_entity="A", counterparty_entity="a", doc_id="x")
