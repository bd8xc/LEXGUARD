from torch.utils.data import DataLoader

from models.dataset import ContractRiskDataset
from models.collate import sliding_window_collate
from models.sliding_legalbert import SlidingWindowLegalBERT

# Load dataset
dataset = ContractRiskDataset("data/train.csv")

# DataLoader
loader = DataLoader(
    dataset,
    batch_size=4,
    shuffle=False,
    collate_fn=sliding_window_collate,
)

# Get one batch
batch = next(iter(loader))

# Create model
model = SlidingWindowLegalBERT()

# Forward pass
logits = model(
    input_ids=batch["input_ids"],
    attention_mask=batch["attention_mask"],
    window_counts=batch["window_counts"],
)

print("Logits shape:", logits.shape)
print(logits)
