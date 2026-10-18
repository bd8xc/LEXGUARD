import os
import json

import numpy as np
import pandas as pd
import torch
import matplotlib.pyplot as plt

from torch.utils.data import DataLoader
from tqdm import tqdm

from sklearn.metrics import (
    accuracy_score,
    precision_recall_fscore_support,
    classification_report,
    confusion_matrix,
    ConfusionMatrixDisplay,
)

from models.config import Config
from models.dataset import ContractRiskDataset
from models.collate import sliding_window_collate
from models.sliding_legalbert import SlidingWindowLegalBERT


##############################################################
# CONFIGURATION
##############################################################

cfg = Config()

device = cfg.device

print("=" * 70)
print("CONTRACT RISK MODEL - TEST SET EVALUATION")
print("=" * 70)

print(f"\nUsing device     : {device}")
print(f"Checkpoint       : {cfg.checkpoint_path}")
print(f"Test dataset     : {cfg.test_csv}")


##############################################################
# LABEL MAPPING
##############################################################

# IMPORTANT:
# This must match the label encoding used during training.
#
# Based on our training setup:
#
# 0 = Seed
# 1 = Low
# 2 = Medium
# 3 = High

LABEL_NAMES = [
    "Seed",
    "Low",
    "Medium",
    "High",
]

ID_TO_LABEL = {
    0: "Seed",
    1: "Low",
    2: "Medium",
    3: "High",
}


##############################################################
# CHECK FILES
##############################################################

if not os.path.exists(cfg.checkpoint_path):

    raise FileNotFoundError(
        f"\nCheckpoint not found:\n"
        f"{cfg.checkpoint_path}\n\n"
        f"Expected structure:\n"
        f"checkpoints/best_model.pt"
    )


if not os.path.exists(cfg.test_csv):

    raise FileNotFoundError(
        f"\nTest dataset not found:\n"
        f"{cfg.test_csv}"
    )


##############################################################
# OUTPUT DIRECTORY
##############################################################

OUTPUT_DIR = "outputs"

os.makedirs(
    OUTPUT_DIR,
    exist_ok=True,
)


##############################################################
# LOAD TEST DATASET
##############################################################

print("\nLoading test dataset...")

test_dataset = ContractRiskDataset(
    csv_path=cfg.test_csv,
    model_name=cfg.model_name,
    max_length=cfg.max_length,
    stride=cfg.stride,
)

print(
    f"Test samples     : {len(test_dataset)}"
)


##############################################################
# TEST DATALOADER
##############################################################

test_loader = DataLoader(
    test_dataset,
    batch_size=cfg.batch_size,
    shuffle=False,
    collate_fn=sliding_window_collate,
)


##############################################################
# CREATE MODEL
##############################################################

print("\nCreating SlidingWindowLegalBERT...")

model = SlidingWindowLegalBERT(
    model_name=cfg.model_name,
    num_classes=cfg.num_classes,
    dropout=cfg.dropout,
)


##############################################################
# LOAD TRAINED CHECKPOINT
##############################################################

print("\nLoading trained checkpoint...")

checkpoint = torch.load(
    cfg.checkpoint_path,
    map_location=device,
    weights_only=False,
)


##############################################################
# SUPPORT BOTH CHECKPOINT FORMATS
##############################################################

if isinstance(checkpoint, dict) and "model_state_dict" in checkpoint:

    model.load_state_dict(
        checkpoint["model_state_dict"]
    )

    checkpoint_epoch = checkpoint.get(
        "epoch",
        "Unknown",
    )

    checkpoint_f1 = checkpoint.get(
        "best_val_f1",
        "Unknown",
    )

else:

    # Handles checkpoint files containing only state_dict

    model.load_state_dict(
        checkpoint
    )

    checkpoint_epoch = "Unknown"

    checkpoint_f1 = "Unknown"


model = model.to(device)

model.eval()


print("\nCheckpoint loaded successfully.")

print(
    f"Saved epoch      : {checkpoint_epoch}"
)

print(
    f"Saved best F1    : {checkpoint_f1}"
)


##############################################################
# STORAGE
##############################################################

all_true_labels = []

all_predictions = []

all_confidences = []

all_probabilities = []


##############################################################
# EVALUATION
##############################################################

print("\nRunning inference on test set...\n")

with torch.no_grad():

    for batch in tqdm(
        test_loader,
        desc="Evaluating",
    ):

        ######################################################
        # MOVE DATA TO DEVICE
        ######################################################

        input_ids = batch[
            "input_ids"
        ].to(device)

        attention_mask = batch[
            "attention_mask"
        ].to(device)

        labels = batch[
            "labels"
        ].to(device)

        window_counts = batch[
            "window_counts"
        ]

        ######################################################
        # FORWARD PASS
        ######################################################

        logits = model(
            input_ids=input_ids,
            attention_mask=attention_mask,
            window_counts=window_counts,
        )

        ######################################################
        # SOFTMAX PROBABILITIES
        ######################################################

        probabilities = torch.softmax(
            logits,
            dim=1,
        )

        ######################################################
        # PREDICTIONS
        ######################################################

        confidence, predictions = torch.max(
            probabilities,
            dim=1,
        )

        ######################################################
        # SAVE RESULTS
        ######################################################

        all_true_labels.extend(
            labels.cpu().numpy()
        )

        all_predictions.extend(
            predictions.cpu().numpy()
        )

        all_confidences.extend(
            confidence.cpu().numpy()
        )

        all_probabilities.extend(
            probabilities.cpu().numpy()
        )


##############################################################
# CONVERT TO NUMPY
##############################################################

all_true_labels = np.array(
    all_true_labels
)

all_predictions = np.array(
    all_predictions
)

all_confidences = np.array(
    all_confidences
)

all_probabilities = np.array(
    all_probabilities
)


##############################################################
# BASIC METRICS
##############################################################

accuracy = accuracy_score(
    all_true_labels,
    all_predictions,
)

macro_precision, macro_recall, macro_f1, _ = (
    precision_recall_fscore_support(
        all_true_labels,
        all_predictions,
        average="macro",
        zero_division=0,
    )
)

weighted_precision, weighted_recall, weighted_f1, _ = (
    precision_recall_fscore_support(
        all_true_labels,
        all_predictions,
        average="weighted",
        zero_division=0,
    )
)


##############################################################
# PRINT METRICS
##############################################################

print("\n" + "=" * 70)

print("TEST SET RESULTS")

print("=" * 70)

print(
    f"\nAccuracy             : {accuracy:.4f}"
)

print(
    f"Macro Precision      : {macro_precision:.4f}"
)

print(
    f"Macro Recall         : {macro_recall:.4f}"
)

print(
    f"Macro F1             : {macro_f1:.4f}"
)

print(
    f"\nWeighted Precision   : {weighted_precision:.4f}"
)

print(
    f"Weighted Recall      : {weighted_recall:.4f}"
)

print(
    f"Weighted F1          : {weighted_f1:.4f}"
)


##############################################################
# CLASSIFICATION REPORT
##############################################################

report = classification_report(
    all_true_labels,
    all_predictions,
    labels=[
        0,
        1,
        2,
        3,
    ],
    target_names=LABEL_NAMES,
    digits=4,
    zero_division=0,
)

print(
    "\nCLASSIFICATION REPORT\n"
)

print(report)


##############################################################
# SAVE CLASSIFICATION REPORT
##############################################################

report_path = os.path.join(
    OUTPUT_DIR,
    "classification_report.txt",
)

with open(
    report_path,
    "w",
    encoding="utf-8",
) as file:

    file.write(
        "CONTRACT RISK PREDICTION\n"
    )

    file.write(
        "TEST SET CLASSIFICATION REPORT\n"
    )

    file.write(
        "=" * 70
    )

    file.write("\n\n")

    file.write(report)


##############################################################
# CONFUSION MATRIX
##############################################################

cm = confusion_matrix(
    all_true_labels,
    all_predictions,
    labels=[
        0,
        1,
        2,
        3,
    ],
)


##############################################################
# SAVE CONFUSION MATRIX CSV
##############################################################

cm_dataframe = pd.DataFrame(
    cm,
    index=[
        f"True_{label}"
        for label in LABEL_NAMES
    ],
    columns=[
        f"Predicted_{label}"
        for label in LABEL_NAMES
    ],
)

cm_csv_path = os.path.join(
    OUTPUT_DIR,
    "confusion_matrix.csv",
)

cm_dataframe.to_csv(
    cm_csv_path
)


##############################################################
# SAVE CONFUSION MATRIX IMAGE
##############################################################

figure, axis = plt.subplots(
    figsize=(8, 7)
)

display = ConfusionMatrixDisplay(
    confusion_matrix=cm,
    display_labels=LABEL_NAMES,
)

display.plot(
    ax=axis,
    values_format="d",
)

axis.set_title(
    "Contract Risk Prediction - Confusion Matrix"
)

plt.tight_layout()

cm_image_path = os.path.join(
    OUTPUT_DIR,
    "confusion_matrix.png",
)

plt.savefig(
    cm_image_path,
    dpi=300,
    bbox_inches="tight",
)

plt.close()


##############################################################
# LOAD ORIGINAL TEST CSV
##############################################################

original_test_df = pd.read_csv(
    cfg.test_csv
)


##############################################################
# VERIFY ROW COUNTS
##############################################################

if len(original_test_df) != len(all_predictions):

    print(
        "\nWARNING:"
        "\nNumber of predictions does not match "
        "number of CSV rows."
    )

    print(
        f"CSV rows     : {len(original_test_df)}"
    )

    print(
        f"Predictions  : {len(all_predictions)}"
    )


##############################################################
# BUILD PREDICTIONS DATAFRAME
##############################################################

results_df = original_test_df.copy()

results_df[
    "true_label_id"
] = all_true_labels

results_df[
    "true_label"
] = [
    ID_TO_LABEL[int(label)]
    for label in all_true_labels
]

results_df[
    "predicted_label_id"
] = all_predictions

results_df[
    "predicted_label"
] = [
    ID_TO_LABEL[int(label)]
    for label in all_predictions
]

results_df[
    "confidence"
] = all_confidences


##############################################################
# ADD PER-CLASS PROBABILITIES
##############################################################

results_df[
    "prob_seed"
] = all_probabilities[:, 0]

results_df[
    "prob_low"
] = all_probabilities[:, 1]

results_df[
    "prob_medium"
] = all_probabilities[:, 2]

results_df[
    "prob_high"
] = all_probabilities[:, 3]


##############################################################
# CORRECT / INCORRECT
##############################################################

results_df[
    "correct"
] = (
    results_df["true_label_id"]
    ==
    results_df["predicted_label_id"]
)


##############################################################
# SAVE ALL PREDICTIONS
##############################################################

predictions_path = os.path.join(
    OUTPUT_DIR,
    "predictions.csv",
)

results_df.to_csv(
    predictions_path,
    index=False,
)


##############################################################
# SAVE MISCLASSIFIED EXAMPLES
##############################################################

errors_df = results_df[
    results_df["correct"] == False
].copy()

errors_df = errors_df.sort_values(
    by="confidence",
    ascending=False,
)

errors_path = os.path.join(
    OUTPUT_DIR,
    "misclassified.csv",
)

errors_df.to_csv(
    errors_path,
    index=False,
)


##############################################################
# CONFIDENCE ANALYSIS
##############################################################

correct_mask = (
    all_true_labels
    ==
    all_predictions
)

incorrect_mask = (
    all_true_labels
    !=
    all_predictions
)


average_confidence = float(
    np.mean(
        all_confidences
    )
)

average_correct_confidence = float(
    np.mean(
        all_confidences[
            correct_mask
        ]
    )
)

if incorrect_mask.sum() > 0:

    average_incorrect_confidence = float(
        np.mean(
            all_confidences[
                incorrect_mask
            ]
        )
    )

else:

    average_incorrect_confidence = 0.0


##############################################################
# SAVE METRICS JSON
##############################################################

metrics = {

    "test_samples":
        int(
            len(
                all_true_labels
            )
        ),

    "correct_predictions":
        int(
            correct_mask.sum()
        ),

    "incorrect_predictions":
        int(
            incorrect_mask.sum()
        ),

    "accuracy":
        float(
            accuracy
        ),

    "macro_precision":
        float(
            macro_precision
        ),

    "macro_recall":
        float(
            macro_recall
        ),

    "macro_f1":
        float(
            macro_f1
        ),

    "weighted_precision":
        float(
            weighted_precision
        ),

    "weighted_recall":
        float(
            weighted_recall
        ),

    "weighted_f1":
        float(
            weighted_f1
        ),

    "average_confidence":
        average_confidence,

    "average_correct_confidence":
        average_correct_confidence,

    "average_incorrect_confidence":
        average_incorrect_confidence,
}


metrics_path = os.path.join(
    OUTPUT_DIR,
    "metrics.json",
)

with open(
    metrics_path,
    "w",
    encoding="utf-8",
) as file:

    json.dump(
        metrics,
        file,
        indent=4,
    )


##############################################################
# SUMMARY
##############################################################

print("\n" + "=" * 70)

print("CONFIDENCE ANALYSIS")

print("=" * 70)

print(
    f"\nAverage confidence             : "
    f"{average_confidence:.4f}"
)

print(
    f"Average confidence (correct)   : "
    f"{average_correct_confidence:.4f}"
)

print(
    f"Average confidence (incorrect) : "
    f"{average_incorrect_confidence:.4f}"
)


print("\n" + "=" * 70)

print("EVALUATION COMPLETE")

print("=" * 70)

print(
    f"\nCorrect predictions   : "
    f"{correct_mask.sum()}"
)

print(
    f"Incorrect predictions : "
    f"{incorrect_mask.sum()}"
)

print(
    "\nGenerated files:"
)

print(
    f"  {metrics_path}"
)

print(
    f"  {report_path}"
)

print(
    f"  {cm_csv_path}"
)

print(
    f"  {cm_image_path}"
)

print(
    f"  {predictions_path}"
)

print(
    f"  {errors_path}"
)