# LE inference package

`litigation_agent.py` defines `LexState`, validates features, loads and caches the XGBoost artifact, and returns predictions. `explainability.py` computes SHAP contributions; `orchestration.py` provides the agent handoff. Training stays in the parent directory.
