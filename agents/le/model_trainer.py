"""
LEXGUARD — Litigation Exposure Agent
Step 3: XGBoost Model Training

Enhanced version:
- Train/Test ROC-AUC comparison
- Overfitting detection
- Threshold analysis
- Class imbalance handling
- SHAP validation
- Feature importance reporting
- Model + feature serialization

Usage:
    python models/train_model.py
"""

import json
from pathlib import Path

import joblib
import pandas as pd
import shap
from tqdm import tqdm

from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    roc_auc_score,
    recall_score,
    precision_score,
    f1_score,
    average_precision_score,
    balanced_accuracy_score,
    brier_score_loss,
    precision_recall_curve,
)

from sklearn.model_selection import train_test_split
from xgboost import XGBClassifier


# ──────────────────────────────────────────────────────────────────────────────
# Paths
# ──────────────────────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parent

DATA_PATH = ROOT / "litigation_training_data.csv"
MODEL_PATH = ROOT / "litigation_model.joblib"
FEAT_PATH = ROOT / "feature_names.json"


# ──────────────────────────────────────────────────────────────────────────────
# Features
# ──────────────────────────────────────────────────────────────────────────────

FEATURE_ORDER = [
    "deal_size",
    "liability_cap",
    "auto_renewal",
    "jurisdiction_risk",
    "conflict_flag",
    "clause_deviation_score",
    "indemnification_clause",
    "dispute_history",
    "governing_law_clarity",
]

TARGET = "litigated"

RECALL_THRESHOLD = 0.75
AUCROC_TARGET = 0.80


# ──────────────────────────────────────────────────────────────────────────────
# Data Loading
# ──────────────────────────────────────────────────────────────────────────────

def load_data(path: Path) -> pd.DataFrame:

    if not path.exists():
        raise FileNotFoundError(
            f"Training data not found at {path}"
        )

    df = pd.read_csv(path)

    print(
        f"[train_model] Loaded {len(df):,} records "
        f"from {path.name}"
    )

    return df


def split_data(df: pd.DataFrame):

    X = df[FEATURE_ORDER]
    y = df[TARGET]

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.20,
        stratify=y,
        random_state=42,
    )

    print(
        f"Train: {len(X_train):,} rows | "
        f"Test: {len(X_test):,} rows"
    )

    print(
        f"Dispute Rate -> "
        f"Train: {y_train.mean():.1%} | "
        f"Test: {y_test.mean():.1%}"
    )

    return X_train, X_test, y_train, y_test


# ──────────────────────────────────────────────────────────────────────────────
# Model
# ──────────────────────────────────────────────────────────────────────────────

def build_model(y_train):
    # NOTE: These hyperparameters were previously 200/6/0.1/0.8, matching
    # the ORIGINAL implementation plan PDF (Agent 3, Section 5). However,
    # the litigation_model.joblib actually shipped in this repo was found
    # (by inspecting model.get_params() on the deployed artifact) to have
    # been trained with the hyperparameters below instead, matching the
    # earlier revised training plan (summarized in README.md), not
    # this script. That meant running `python model_trainer.py` would NOT
    # reproduce the model actually being served -- there was no way to
    # regenerate the production model from what was checked into the repo.
    #
    # This has been corrected to match the deployed artifact. If you need
    # to go back to the original PDF's spec (200/6/0.1, no scale_pos_weight
    # or colsample_bytree), do so deliberately and retrain+redeploy the
    # model together so the two stay in sync.
    model = XGBClassifier(
        n_estimators=120,
        max_depth=3,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        scale_pos_weight=1.75,
        objective="binary:logistic",
        eval_metric="logloss",
        random_state=42,
        n_jobs=-1,
    )

    return model


def train(model,X_train,y_train,X_test,y_test):

    print("\nTraining XGBoost...")

    model.fit(
        X_train,
        y_train,
        eval_set=[(X_test, y_test)],
        verbose=10,
    )

    print("Training complete.")

    return model


# ──────────────────────────────────────────────────────────────────────────────
# Threshold Analysis
# ──────────────────────────────────────────────────────────────────────────────

def threshold_analysis(y_true, probabilities):

    precision, recall, thresholds = precision_recall_curve(
        y_true,
        probabilities,
    )

    best_threshold = 0.50
    best_recall = 0.0
    best_precision = 0.0

    for p, r, t in zip(
        precision[:-1],
        recall[:-1],
        thresholds
    ):

        if p >= 0.60 and r > best_recall:
            best_threshold = float(t)
            best_recall = float(r)
            best_precision = float(p)

    print("\nThreshold Analysis")
    print("-" * 60)
    print(f"Suggested Threshold : {best_threshold:.3f}")
    print(f"Recall              : {best_recall:.3f}")
    print(f"Precision           : {best_precision:.3f}")

    return best_threshold


# ──────────────────────────────────────────────────────────────────────────────
# Evaluation
# ──────────────────────────────────────────────────────────────────────────────

def evaluate(
    model,
    X_train,
    X_test,
    y_train,
    y_test
):

    train_probs = model.predict_proba(X_train)[:, 1]
    test_probs = model.predict_proba(X_test)[:, 1]

    train_auc = roc_auc_score(
        y_train,
        train_probs
    )

    test_auc = roc_auc_score(
        y_test,
        test_probs
    )

    y_pred = model.predict(X_test)

    recall = recall_score(
        y_test,
        y_pred
    )

    precision = precision_score(
        y_test,
        y_pred
    )

    f1 = f1_score(
        y_test,
        y_pred
    )

    pr_auc = average_precision_score(y_test, test_probs)
    balanced_accuracy = balanced_accuracy_score(y_test, y_pred)
    brier = brier_score_loss(y_test, test_probs)

    print("\nEvaluation Results")
    print("=" * 60)

    print(f"Train ROC-AUC : {train_auc:.4f}")
    print(f"Test ROC-AUC  : {test_auc:.4f}")

    auc_gap = train_auc - test_auc

    print(f"AUC Gap       : {auc_gap:.4f}")

    if auc_gap > 0.10:
        print(
            "\n[WARN] Potential overfitting detected."
        )

    print("\nCore Metrics")
    print("-" * 60)

    print(f"Recall        : {recall:.4f}")
    print(f"Precision     : {precision:.4f}")
    print(f"F1 Score      : {f1:.4f}")
    print(f"PR-AUC        : {pr_auc:.4f}")
    print(f"Balanced Acc. : {balanced_accuracy:.4f}")
    print(f"Brier Score   : {brier:.4f}")

    print("\nClassification Report")
    print("-" * 60)

    print(
        classification_report(
            y_test,
            y_pred,
            target_names=[
                "No Dispute",
                "Dispute"
            ]
        )
    )

    print("Confusion Matrix")
    print("-" * 60)

    cm = confusion_matrix(
        y_test,
        y_pred
    )

    print(cm)

    threshold_analysis(
        y_test,
        test_probs
    )

    print("\nFeature Importances")
    print("-" * 60)

    feature_importances = dict(
        zip(
            FEATURE_ORDER,
            model.feature_importances_
        )
    )

    for feat, score in sorted(
        feature_importances.items(),
        key=lambda x: x[1],
        reverse=True
    ):

        bar = "#" * int(score * 40)

        print(
            f"{feat:<26} "
            f"{score:.4f} "
            f"{bar}"
        )

    if recall < RECALL_THRESHOLD:
        raise RuntimeError(
            f"\n[FAIL] Recall "
            f"{recall:.4f} "
            f"< required "
            f"{RECALL_THRESHOLD}"
        )

    if test_auc < AUCROC_TARGET:

        print(
            f"\n[WARN] Test ROC-AUC "
            f"{test_auc:.4f} "
            f"< target "
            f"{AUCROC_TARGET}"
        )

    else:

        print(
            "\n[PASS] Model meets "
            "synthetic validation thresholds."
        )


# ──────────────────────────────────────────────────────────────────────────────
# SHAP Validation
# ──────────────────────────────────────────────────────────────────────────────

def validate_shap(model, X_test):

    print("\nValidating SHAP...")

    sample = X_test.iloc[:1]

    explainer = shap.TreeExplainer(
        model
    )

    shap_values = explainer.shap_values(
        sample
    )

    print(
        f"SHAP validation passed "
        f"({len(shap_values[0])} features)"
    )


# ──────────────────────────────────────────────────────────────────────────────
# Save Artifacts
# ──────────────────────────────────────────────────────────────────────────────

def save_artifacts(model):

    ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    joblib.dump(
        model,
        MODEL_PATH,
    )

    print(
        f"\nModel saved -> "
        f"{MODEL_PATH}"
    )

    with open(
        FEAT_PATH,
        "w"
    ) as f:

        json.dump(
            FEATURE_ORDER,
            f,
            indent=2,
        )

    print(
        f"Features saved -> "
        f"{FEAT_PATH}"
    )


# ──────────────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────────────

def main():

    print("=" * 70)
    print(
        "LEXGUARD — Litigation Exposure Agent "
        "Model Training"
    )
    print("=" * 70)

    steps = [
        "Load Dataset",
        "Split Dataset",
        "Build Model",
        "Train Model",
        "Evaluate Model",
        "Validate SHAP",
        "Save Artifacts",
    ]

    pbar = tqdm(
        total=len(steps),
        desc="Pipeline Progress",
        unit="step"
    )

    df = load_data(DATA_PATH)
    pbar.update(1)

    X_train, X_test, y_train, y_test = split_data(df)
    pbar.update(1)

    model = build_model(y_train)
    pbar.update(1)

    model = train(
        model,
        X_train,
        y_train,
        X_test,
        y_test,
    )
    pbar.update(1)

    evaluate(
        model,
        X_train,
        X_test,
        y_train,
        y_test,
    )
    pbar.update(1)

    validate_shap(
        model,
        X_test,
    )
    pbar.update(1)

    save_artifacts(
        model,
    )
    pbar.update(1)

    pbar.close()

    print("\nTraining pipeline complete.")

if __name__ == "__main__":
    main()
