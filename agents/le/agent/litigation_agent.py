from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import joblib
import pandas as pd

from .explainability import explain_prediction


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL_PATH = PROJECT_ROOT / "litigation_model.joblib"
DEFAULT_FEATURE_PATH = PROJECT_ROOT / "feature_names.json"

_MODEL_CACHE: dict[str, tuple[Any, str]] = {}
_MODEL_CACHE_LOCK = threading.Lock()


def _fingerprint_file(path: Path) -> str:
    """Cheap content fingerprint so the cache key changes if the file is replaced."""
    stat = path.stat()
    hasher = hashlib.sha256()
    hasher.update(str(stat.st_mtime_ns).encode())
    hasher.update(str(stat.st_size).encode())
    return hasher.hexdigest()[:16]


def _load_model_cached(model_path: Path) -> tuple[Any, str]:
    """Load (and cache) the model, keyed on path + fingerprint.

    If the underlying file changes (new mtime/size -- e.g. a redeploy wrote
    a fresh joblib) the fingerprint changes and we transparently reload,
    instead of either reloading on every call or silently serving a stale
    in-memory model forever.
    """
    fingerprint = _fingerprint_file(model_path)
    cache_key = f"{model_path}:{fingerprint}"

    with _MODEL_CACHE_LOCK:
        cached = _MODEL_CACHE.get(cache_key)
        if cached is not None:
            return cached

        model = joblib.load(model_path)
        _MODEL_CACHE.clear()  # only keep the current model version resident
        _MODEL_CACHE[cache_key] = (model, fingerprint)
        return model, fingerprint


# Inputs arrive through a shared LexState.
# Contract features live in state.entities;
# graph-derived values, including conflict_flag, live in state.graph_results.
@dataclass
class LexState:
    contract_text: str = ""
    entities: dict[str, Any] = field(default_factory=dict)
    graph_results: dict[str, Any] = field(default_factory=dict)
    clause_deviation_score: float | None = None
    litigation_probability: float | None = None
    final_risk_score: float | None = None
    model_fingerprint: str | None = None


class LitigationExposureAgent:
    def __init__(self, model_path: Path | str = DEFAULT_MODEL_PATH, feature_path: Path | str = DEFAULT_FEATURE_PATH):
        self.model_path = Path(model_path)
        self.model, self.model_fingerprint = _load_model_cached(self.model_path)
        with Path(feature_path).open(encoding="utf-8") as stream:
            self.feature_order: list[str] = json.load(stream)

    def extract_features(self, state: LexState) -> dict[str, float]:
        sources = {**state.entities, **state.graph_results}
        sources["clause_deviation_score"] = state.clause_deviation_score
        missing = [name for name in self.feature_order if sources.get(name) is None]
        if missing:
            raise ValueError(f"Missing required litigation features: {', '.join(missing)}")
        features = {name: float(sources[name]) for name in self.feature_order}
        self._validate(features)
        return features

    @staticmethod
    def _validate(features: dict[str, float]) -> None:
        ranges = {
            "deal_size": (50_000, 5_000_000), "liability_cap": (0, 1),
            "auto_renewal": (0, 1), "jurisdiction_risk": (1, 10),
            "conflict_flag": (0, 1), "clause_deviation_score": (0, 1),
            "indemnification_clause": (0, 1), "dispute_history": (0, 1),
            "governing_law_clarity": (1, 5),
        }
        invalid = [name for name, value in features.items() if name in ranges and not ranges[name][0] <= value <= ranges[name][1]]
        if invalid:
            raise ValueError(f"Out-of-range litigation features: {', '.join(invalid)}")

    def _predict(self, features: dict[str, float], model: Any | None = None) -> float:
        frame = pd.DataFrame([[features[name] for name in self.feature_order]], columns=self.feature_order)
        return float((model or self.model).predict_proba(frame)[0, 1])

    @staticmethod
    def interpret_probability(probability: float) -> str:
        if probability < 0.30:
            return "Low"
        if probability < 0.60:
            return "Medium"
        return "High"

    def run(self, state: LexState) -> LexState:
        probability = self._predict(self.extract_features(state), model=self.model)
        state.litigation_probability = round(probability, 4)
        state.model_fingerprint = self.model_fingerprint
        return state

    def predict_with_explanation(self, state: LexState) -> dict[str, Any]:
        features = self.extract_features(state)
        # Snapshot the model reference once so probability and SHAP are
        # guaranteed to come from the exact same object, even if a
        # concurrent reload swaps self.model on this instance mid-call.
        model = self.model
        probability = self._predict(features, model=model)
        shap_explanation = explain_prediction(model, features, self.feature_order)
        return {
            "litigation_probability": round(probability, 4),
            "risk_level": self.interpret_probability(probability),
            "features_used": features,
            "shap_explanation": shap_explanation,
            "model_fingerprint": self.model_fingerprint,
        }