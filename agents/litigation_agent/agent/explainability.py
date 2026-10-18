"""SHAP explanations for Litigation Exposure Agent predictions."""

from __future__ import annotations

from typing import Mapping

import pandas as pd
import shap


def explain_prediction(model, features: Mapping[str, float], feature_order: list[str]) -> dict[str, float]:
    """Return each feature's SHAP contribution to the positive litigation class."""
    frame = pd.DataFrame([[features[name] for name in feature_order]], columns=feature_order)
    values = shap.TreeExplainer(model).shap_values(frame)
    # SHAP versions return either (rows, features) or (rows, features, classes).
    if getattr(values, "ndim", 0) == 3:
        values = values[:, :, 1]
    return {name: round(float(value), 6) for name, value in zip(feature_order, values[0])}
