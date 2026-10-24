import torch


def sliding_window_collate(batch):
    """
    Custom collate function for clauses with a variable
    number of sliding windows.
    """

    input_ids = []
    attention_masks = []

    labels = []

    window_counts = []

    for sample in batch:

        input_ids.append(sample["input_ids"])

        attention_masks.append(sample["attention_mask"])

        labels.append(sample["label"])

        window_counts.append(sample["num_windows"])

    input_ids = torch.cat(input_ids, dim=0)

    attention_masks = torch.cat(attention_masks, dim=0)

    labels = torch.stack(labels)

    window_counts = torch.tensor(window_counts)

    return {
        "input_ids": input_ids,
        "attention_mask": attention_masks,
        "labels": labels,
        "window_counts": window_counts,
    }