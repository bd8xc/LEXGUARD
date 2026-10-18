# Contract Risk Analysis (CRA)

CRA is the clause-level legal-risk analysis agent. It combines a fine-tuned
LegalBERT classifier, Indian-law retrieval, and a local Ollama model that
explains clauses selected for review. The LegalBERT prediction is the model
signal; the LLM explanation is a separate assessment and should be reviewed by
a qualified person.

## Integrated contract workflow

The root FastAPI application coordinates CRA with CL, COI, and optional LE.
From the repository root, install [`requirements.txt`](../../requirements.txt),
configure `.env`, ensure Ollama and the CRA checkpoint are available, then run:

```powershell
python -m uvicorn api:app --reload
```

Use the browser at `http://127.0.0.1:8000` or submit a contract through
`POST /analyze-contract` in Swagger at `/docs`. CRA segments the document,
predicts a risk band per eligible clause, and asks the LLM to analyze clauses
above the model baseline or selected by CL. The response includes the ML
prediction, score, and clause LLM output.

The local explanation model defaults to Ollama's `qwen2.5:1.5b`. Start Ollama
and download it with `ollama pull qwen2.5:1.5b`. The first analysis also
downloads LegalBERT and the configured sentence-transformer embedding model
from Hugging Face if they are not already cached.

## CRA checkpoint

Inference expects the fine-tuned checkpoint here:

```text
agents/cra/checkpoints/best_model.pt
```

The checkpoint is approximately 1.3 GB and is excluded from the root Git
repository. Obtain the approved artifact from the project maintainer or create
one by training. A normal GitHub clone will not contain this file.

## Training and evaluation

Training and evaluation code, datasets, model architecture, and configuration
are kept in this folder. Start these commands from `agents/cra` after installing
the root requirements and preparing the training CSV files:

```powershell
python train.py
python evaluate.py
```

Training writes checkpoints and evaluation outputs under this folder. Those
generated artifacts are ignored by the root `.gitignore`.

## Main components

- `models/`: sliding-window LegalBERT architecture, datasets, inference, and training.
- `processing/`: clause segmentation and model risk resolution/validation.
- `rag/` and `knowledge_base/`: Indian legal corpus retrieval and embeddings.
- `llm/local_llm.py`: local Ollama client and structured CRA explanations.
- `orchestration/contract_pipeline.py`: document-level integration with the other agents.

CRA results are experimental risk signals, not legal conclusions or a
substitute for counsel. Retrieved legal text and generated explanations need
human verification.
