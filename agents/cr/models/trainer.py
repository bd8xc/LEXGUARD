import os

import torch
from tqdm import tqdm

from sklearn.metrics import (
    accuracy_score,
    precision_recall_fscore_support,
)

from torch.utils.tensorboard import SummaryWriter


class Trainer:
    """
    Trainer for SW-LegalBERT

    Responsibilities
    ----------------
    1. Training
    2. Validation
    3. Checkpoint Saving
    4. Early Stopping
    5. TensorBoard Logging
    """

    def __init__(
    self,
    model,
    tokenizer,
    train_loader,
    val_loader,
    optimizer,
    scheduler,
    criterion,
    device,
    checkpoint_dir="checkpoints",
    patience=3,
):
        self.model = model.to(device)

        self.train_loader = train_loader
        self.val_loader = val_loader

        self.optimizer = optimizer
        self.scheduler = scheduler
        self.criterion = criterion

        self.device = device

        self.best_val_f1 = 0.0

        self.patience = patience
        self.counter = 0

        self.checkpoint_dir = checkpoint_dir

        os.makedirs(
            self.checkpoint_dir,
            exist_ok=True,
        )

        self.writer = SummaryWriter(
            "runs/contract_risk"
        )

    #########################################################
    # TRAIN FOR ONE EPOCH
    #########################################################

    def train_epoch(self):

        self.model.train()

        running_loss = 0.0

        predictions = []
        labels = []

        progress = tqdm(
            self.train_loader,
            desc="Training",
            leave=False,
        )

        for batch in progress:

            input_ids = batch["input_ids"].to(
                self.device
            )

            attention_mask = batch[
                "attention_mask"
            ].to(self.device)

            window_counts = batch[
                "window_counts"
            ]

            targets = batch["labels"].to(
                self.device
            )

            #################################################
            # FORWARD
            #################################################

            logits = self.model(
                input_ids=input_ids,
                attention_mask=attention_mask,
                window_counts=window_counts,
            )

            loss = self.criterion(
                logits,
                targets,
            )

            #################################################
            # BACKWARD
            #################################################

            self.optimizer.zero_grad()

            loss.backward()

            torch.nn.utils.clip_grad_norm_(
                self.model.parameters(),
                max_norm=1.0,
            )

            self.optimizer.step()

            if self.scheduler is not None:
                self.scheduler.step()

            #################################################
            # METRICS
            #################################################

            running_loss += loss.item()

            preds = torch.argmax(
                logits,
                dim=1,
            )

            predictions.extend(
                preds.cpu().numpy()
            )

            labels.extend(
                targets.cpu().numpy()
            )

            progress.set_postfix(
                loss=f"{loss.item():.4f}"
            )

        #####################################################
        # EPOCH METRICS
        #####################################################

        accuracy = accuracy_score(
            labels,
            predictions,
        )

        precision, recall, f1, _ = (
            precision_recall_fscore_support(
                labels,
                predictions,
                average="weighted",
                zero_division=0,
            )
        )

        metrics = {
            "loss": running_loss
            / len(self.train_loader),
            "accuracy": accuracy,
            "precision": precision,
            "recall": recall,
            "f1": f1,
        }

        return metrics

    #########################################################
    # VALIDATION
    #########################################################

    def validate(self):

        self.model.eval()

        running_loss = 0.0

        predictions = []
        labels = []

        with torch.no_grad():

            progress = tqdm(
                self.val_loader,
                desc="Validation",
                leave=False,
            )

            for batch in progress:

                input_ids = batch[
                    "input_ids"
                ].to(self.device)

                attention_mask = batch[
                    "attention_mask"
                ].to(self.device)

                window_counts = batch[
                    "window_counts"
                ]

                targets = batch[
                    "labels"
                ].to(self.device)

                logits = self.model(
                    input_ids=input_ids,
                    attention_mask=attention_mask,
                    window_counts=window_counts,
                )

                loss = self.criterion(
                    logits,
                    targets,
                )

                running_loss += loss.item()

                preds = torch.argmax(
                    logits,
                    dim=1,
                )

                predictions.extend(
                    preds.cpu().numpy()
                )

                labels.extend(
                    targets.cpu().numpy()
                )

        accuracy = accuracy_score(
            labels,
            predictions,
        )

        precision, recall, f1, _ = (
            precision_recall_fscore_support(
                labels,
                predictions,
                average="weighted",
                zero_division=0,
            )
        )

        metrics = {
            "loss": running_loss
            / len(self.val_loader),
            "accuracy": accuracy,
            "precision": precision,
            "recall": recall,
            "f1": f1,
        }

        return metrics
    
        #########################################################
    # SAVE CHECKPOINT
    #########################################################

    def save_checkpoint(
        self,
        epoch,
        val_metrics,
    ):
        """
        Saves everything needed to resume training.
        """

        checkpoint = {
            "epoch": epoch,
            "model_state_dict": self.model.state_dict(),
            "optimizer_state_dict": self.optimizer.state_dict(),
            "scheduler_state_dict": (
                self.scheduler.state_dict()
                if self.scheduler is not None
                else None
            ),
            "best_val_f1": self.best_val_f1,
            "metrics": val_metrics,
        }

        save_path = os.path.join(
            self.checkpoint_dir,
            "best_model.pt",
        )

        torch.save(
            checkpoint,
            save_path,
        )

        print(f"\n✓ Checkpoint saved to {save_path}")

    #########################################################
    # LOAD CHECKPOINT
    #########################################################

    def load_checkpoint(
        self,
        checkpoint_path,
    ):
        """
        Resume training from a saved checkpoint.
        """

        checkpoint = torch.load(
            checkpoint_path,
            map_location=self.device,
        )

        self.model.load_state_dict(
            checkpoint["model_state_dict"]
        )

        self.optimizer.load_state_dict(
            checkpoint["optimizer_state_dict"]
        )

        if (
            self.scheduler is not None
            and checkpoint["scheduler_state_dict"] is not None
        ):
            self.scheduler.load_state_dict(
                checkpoint["scheduler_state_dict"]
            )

        self.best_val_f1 = checkpoint["best_val_f1"]

        print(
            f"\nLoaded checkpoint from epoch {checkpoint['epoch'] + 1}"
        )

        return checkpoint["epoch"] + 1

    #########################################################
    # TRAIN LOOP
    #########################################################

    def train(
        self,
        epochs,
        start_epoch=0,
    ):

        for epoch in range(start_epoch, epochs):

            print("\n" + "=" * 70)
            print(f"Epoch {epoch + 1}/{epochs}")
            print("=" * 70)

            #############################################
            # TRAIN
            #############################################

            train_metrics = self.train_epoch()

            #############################################
            # VALIDATE
            #############################################

            val_metrics = self.validate()

            #############################################
            # TENSORBOARD
            #############################################

            self.writer.add_scalar(
                "Loss/Train",
                train_metrics["loss"],
                epoch,
            )

            self.writer.add_scalar(
                "Loss/Validation",
                val_metrics["loss"],
                epoch,
            )

            self.writer.add_scalar(
                "Accuracy/Validation",
                val_metrics["accuracy"],
                epoch,
            )

            self.writer.add_scalar(
                "F1/Validation",
                val_metrics["f1"],
                epoch,
            )

            #############################################
            # PRINT RESULTS
            #############################################

            print("\nTraining")

            for key, value in train_metrics.items():
                print(
                    f"{key:12}: {value:.4f}"
                )

            print("\nValidation")

            for key, value in val_metrics.items():
                print(
                    f"{key:12}: {value:.4f}"
                )

            #############################################
            # EARLY STOPPING
            #############################################

            if val_metrics["f1"] > self.best_val_f1:

                self.best_val_f1 = val_metrics["f1"]

                self.counter = 0

                self.save_checkpoint(
                    epoch,
                    val_metrics,
                )

                print("\n✓ New Best Model")

            else:

                self.counter += 1

                print(
                    f"\nNo improvement ({self.counter}/{self.patience})"
                )

                if self.counter >= self.patience:

                    print("\nEarly stopping triggered.")

                    break

        #############################################
        # CLOSE TENSORBOARD
        #############################################

        self.writer.close()

        print("\nTraining Finished.")