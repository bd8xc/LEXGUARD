import pandas as pd
import torch
from torch.utils.data import Dataset
from transformers import AutoTokenizer


class ContractRiskDataset(Dataset):
    """
    Dataset for loading legal clauses and converting them into
    sliding-window tokenized inputs.
    """

    def __init__(
        self,
        csv_path: str,
        model_name: str = "nlpaueb/legal-bert-base-uncased",
        max_length: int = 512,
        stride: int = 128,
    ):

        self.df = pd.read_csv(csv_path)

        self.tokenizer = AutoTokenizer.from_pretrained(model_name)

        self.max_length = max_length
        self.stride = stride

    def __len__(self):

        return len(self.df)

    def __getitem__(self, idx):

        row = self.df.iloc[idx]

        text = str(row["text"])

        label = int(row["label"])

        encoding = self.tokenizer(
            text,
            max_length=self.max_length,
            truncation=True,
            stride=self.stride,
            return_overflowing_tokens=True,
            padding="max_length",
            return_tensors="pt",
        )

        return {
    "input_ids": encoding["input_ids"],
    "attention_mask": encoding["attention_mask"],
    "label": torch.tensor(label),
    "num_windows": encoding["input_ids"].shape[0]
}
