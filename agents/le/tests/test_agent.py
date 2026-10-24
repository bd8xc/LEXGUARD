import pytest

from le import LexState, LitigationExposureAgent


@pytest.fixture(scope="module")
def agent():
    return LitigationExposureAgent()


def state(**overrides):
    entities = {
        "deal_size": 500_000, "liability_cap": 0, "auto_renewal": 1,
        "jurisdiction_risk": 6, "indemnification_clause": 0,
        "dispute_history": 0, "governing_law_clarity": 3,
    }
    graph_results = {"conflict_flag": 0}
    entities.update(overrides.pop("entities", {}))
    graph_results.update(overrides.pop("graph_results", {}))
    clause_deviation_score = overrides.pop("clause_deviation_score", 0.35)
    return LexState(
        entities=entities,
        graph_results=graph_results,
        clause_deviation_score=clause_deviation_score,
        **overrides,
    )


def test_high_risk_contract(agent):
    result = agent.predict_with_explanation(state(
        entities={"deal_size": 2_000_000, "liability_cap": 0, "jurisdiction_risk": 9,
                  "dispute_history": 1, "governing_law_clarity": 1},
        graph_results={"conflict_flag": 1}, clause_deviation_score=0.85,
    ))
    assert result["litigation_probability"] > 0.60
    assert result["risk_level"] == "High"
    assert set(result["shap_explanation"]) == set(agent.feature_order)


def test_low_risk_contract(agent):
    result = agent.predict_with_explanation(state(
        entities={"deal_size": 50_000, "liability_cap": 1, "auto_renewal": 0,
                  "jurisdiction_risk": 1, "indemnification_clause": 1,
                  "dispute_history": 0, "governing_law_clarity": 5},
        graph_results={"conflict_flag": 0}, clause_deviation_score=0.02,
    ))
    assert result["litigation_probability"] < 0.40
    assert result["risk_level"] == "Low"


def test_output_stays_in_range(agent):
    assert 0.0 <= agent.run(state()).litigation_probability <= 1.0


def test_missing_upstream_value_is_rejected(agent):
    with pytest.raises(ValueError, match="conflict_flag"):
        agent.run(state(graph_results={"conflict_flag": None}))
