from coordinator import AnalyzeRequest, _run_le


def test_coi_flag_is_passed_to_litigation_agent():
    request = AnalyzeRequest(
        client_entity="Alpha",
        counterparty_entity="Beta",
        contract_text="A contract clause long enough for the integrated coordinator test.",
        features={
            "deal_size": 750_000, "liability_cap": 0, "auto_renewal": 1,
            "jurisdiction_risk": 8, "indemnification_clause": 0,
            "dispute_history": 1, "governing_law_clarity": 2,
        },
    )
    result = _run_le(request, conflict_flag=1, deviation=0.7)
    assert result["features_used"]["conflict_flag"] == 1.0
    assert 0.0 <= result["litigation_probability"] <= 1.0
