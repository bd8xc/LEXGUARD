from models.dataset import ContractRiskDataset

dataset = ContractRiskDataset("data/train.csv")

print(f"Dataset size: {len(dataset)}")

print("-" * 60)

max_windows = 0
max_idx = -1

for i in range(len(dataset)):
    sample = dataset[i]

    windows = sample["input_ids"].shape[0]

    if windows > max_windows:
        max_windows = windows
        max_idx = i

print(f"Maximum windows found: {max_windows}")
print(f"Sample index: {max_idx}")

sample = dataset[max_idx]

print()

print("Input IDs Shape:")
print(sample["input_ids"].shape)

print()

print("Attention Mask Shape:")
print(sample["attention_mask"].shape)

print()

print("Label:")
print(sample["label"])