import os
import random

import numpy as np
import torch
import torch.nn as nn

from torch.utils.data import DataLoader
from transformers import get_linear_schedule_with_warmup

from models.config import Config
from models.dataset import ContractRiskDataset
from models.collate import sliding_window_collate
from models.sliding_legalbert import SlidingWindowLegalBERT
from models.trainer import Trainer


##############################################################
# CONFIG
##############################################################

cfg = Config()

##############################################################
# RANDOM SEED
##############################################################

random.seed(cfg.seed)
np.random.seed(cfg.seed)

torch.manual_seed(cfg.seed)

if torch.cuda.is_available():
    torch.cuda.manual_seed_all(cfg.seed)

##############################################################
# DEVICE
##############################################################

device = cfg.device

print(f"Using Device : {device}")

##############################################################
# DATASETS
##############################################################

train_dataset = ContractRiskDataset(
    csv_path=cfg.train_csv,
    model_name=cfg.model_name,
    max_length=cfg.max_length,
    stride=cfg.stride,
)

val_dataset = ContractRiskDataset(
    csv_path=cfg.val_csv,
    model_name=cfg.model_name,
    max_length=cfg.max_length,
    stride=cfg.stride,
)
tokenizer = train_dataset.tokenizer
##############################################################
# DATALOADERS
##############################################################
train_loader = DataLoader(
    train_dataset,
    batch_size=cfg.batch_size,
    shuffle=True,
    collate_fn=sliding_window_collate,
)

val_loader = DataLoader(
    val_dataset,
    batch_size=cfg.batch_size,
    shuffle=False,
    collate_fn=sliding_window_collate,
)
##############################################################
# MODEL
##############################################################

model = SlidingWindowLegalBERT(
    model_name=cfg.model_name,
    num_classes=cfg.num_classes,
    dropout=cfg.dropout,
)

##############################################################
# LOSS
##############################################################

weights = torch.tensor(
    cfg.class_weights,
    dtype=torch.float,
).to(device)

criterion = nn.CrossEntropyLoss(
    weight=weights
)

##############################################################
# OPTIMIZER
##############################################################

optimizer = torch.optim.AdamW(
    model.parameters(),
    lr=cfg.learning_rate,
    weight_decay=cfg.weight_decay,
)

##############################################################
# SCHEDULER
##############################################################

total_steps = len(train_loader) * cfg.epochs

scheduler = get_linear_schedule_with_warmup(
    optimizer,
    num_warmup_steps=int(
        cfg.warmup_ratio * total_steps
    ),
    num_training_steps=total_steps,
)

##############################################################
# TRAINER
##############################################################

trainer = Trainer(
    model=model,
    tokenizer=tokenizer,
    train_loader=train_loader,
    val_loader=val_loader,
    optimizer=optimizer,
    scheduler=scheduler,
    criterion=criterion,
    device=device,
    checkpoint_dir=cfg.checkpoint_dir,
    patience=cfg.patience,
)

##############################################################
# RESUME
##############################################################

start_epoch = 0

if (
    cfg.resume_training
    and os.path.exists(cfg.checkpoint_path)
):

    start_epoch = trainer.load_checkpoint(
        cfg.checkpoint_path
    )

##############################################################
# TRAIN
##############################################################

trainer.train(
    epochs=cfg.epochs,
    start_epoch=start_epoch,
)