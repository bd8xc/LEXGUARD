import torch
import torch.nn as nn

from transformers import AutoModel


class SlidingWindowLegalBERT(nn.Module):
    """
    Sliding Window LegalBERT for long legal clauses.

    Workflow:
        Windows
            ↓
        Shared LegalBERT
            ↓
        CLS embeddings
            ↓
        Mean Pooling
            ↓
        Dropout
            ↓
        Linear Classifier
    """

    def __init__(
        self,
        model_name: str = "nlpaueb/legal-bert-base-uncased",
        num_classes: int = 4,
        dropout: float = 0.1,
    ):
        super().__init__()

        # Pretrained LegalBERT
        self.bert = AutoModel.from_pretrained(model_name)

        # Hidden size (768 for BERT)
        hidden_size = self.bert.config.hidden_size

        # Dropout layer
        self.dropout = nn.Dropout(dropout)

        # Final classifier
        self.classifier = nn.Linear(
            hidden_size,
            num_classes
        )

    def mean_pool(self, cls_embeddings, window_counts):
        """
        Groups window embeddings back into their
        original clauses using mean pooling.

        Parameters
        ----------
        cls_embeddings : Tensor
            Shape:
                (total_windows, hidden_size)

        window_counts : Tensor
            Example:
                [1, 1, 19, 1]

        Returns
        -------
        Tensor
            Shape:
                (batch_size, hidden_size)
        """

        clause_embeddings = []

        start = 0

        for count in window_counts:

            end = start + count.item()

            pooled = cls_embeddings[start:end].mean(dim=0)

            clause_embeddings.append(pooled)

            start = end

        return torch.stack(clause_embeddings)

    def forward(
        self,
        input_ids,
        attention_mask,
        window_counts,
    ):
        """
        Parameters
        ----------
        input_ids
            Shape:
                (total_windows, 512)

        attention_mask
            Shape:
                (total_windows, 512)

        window_counts
            Example:
                [1, 1, 19, 1]

        Returns
        -------
        logits
            Shape:
                (batch_size, num_classes)
        """

        outputs = self.bert(
            input_ids=input_ids,
            attention_mask=attention_mask,
        )

        # CLS token from every window
        cls_embeddings = outputs.last_hidden_state[:, 0, :]

        # Mean pooling across windows belonging
        # to the same clause
        clause_embeddings = self.mean_pool(
            cls_embeddings,
            window_counts,
        )

        # Regularization
        clause_embeddings = self.dropout(
            clause_embeddings
        )

        # Final classification
        logits = self.classifier(
            clause_embeddings
        )

        return logits