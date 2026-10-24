# Litigation Exposure (LE)

LE loads a local XGBoost model, validates the nine-feature input, predicts a litigation exposure score, and returns SHAP contributions. The score comes from synthetic training labels and is not a calibrated real-world litigation probability.

The root coordinator calls LE only after COI completes and an externally measured `clause_deviation_score` is supplied. `conflict_flag` comes from COI. The other contract features are `deal_size`, `liability_cap`, `auto_renewal`, `jurisdiction_risk`, `indemnification_clause`, `dispute_history`, and `governing_law_clarity`.

The unified Swagger UI includes `/api/le/predict` for isolated tests with caller-supplied graph results, `/api/risk/assess` for a COI-to-LE handoff, and `/api/analyze` for the full review.

Run a standalone example from the repository root:

```powershell
.\.venv\Scripts\python.exe -m le.run_litigation_agent --input agents/le/example_litigation_input.json
```

`agent/` contains inference, explanations, and orchestration; `model_trainer.py` and `data_generator.py` support offline model work. `litigation_model.joblib` and `feature_names.json` are the current local artifacts. See the root [README](../../README.md) for installation.
