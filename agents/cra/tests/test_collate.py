from models.dataset import ContractRiskDataset
from models.collate import sliding_window_collate

dataset = ContractRiskDataset("data/train.csv")

batch = [
    dataset[0],
    dataset[10],
    dataset[791],   # <-- longest clause
    dataset[20]
]

output = sliding_window_collate(batch)

print("Input IDs:", output["input_ids"].shape)
print("Attention:", output["attention_mask"].shape)
print("Labels:", output["labels"])
print("Window Counts:", output["window_counts"])