# Confidentiality Leakage (CL)

The `ConfidentialityLeakageAgent` scans contract clauses for structured
identifiers and terms indicating personal data, sensitive personal data,
business-confidential information, processing activities, and contextual
entities. It combines independent detectors, deduplicates/classifies findings,
and produces its own bounded 0-100 confidentiality `risk_score` and
`risk_level`.

In the contract API, CL scans the segmented document once. The browser shows
the agent's risk score/band, counts by sensitivity and data category, and a
findings table with clause/line locations and masked evidence. Processing
activities are presented as handling context, not as proof of a leak.

The report contains raw finding values in memory for programmatic use. Mask
them before returning reports outside a trusted local workflow. Context-
dependent NER matches alone do not establish a leak. NER uses a narrow local
fallback; deterministic detectors continue to run if optional NLP packages or
models are absent.

Direct analysis does not require ChromaDB:

```python
from agents.cl.confidentiality_leakage import ConfidentialityLeakageAgent

agent = ConfidentialityLeakageAgent()
report = agent.analyze(
    doc_id="contract-001",
    clauses=[{"clause_id": "4.2", "text": "Paste clause text here."}],
)
print(report.model_dump())
```

The optional indexed-document router requires the separate LDI vector-store
package and is not mounted by the contract API. Direct CL analysis does not
require ChromaDB or another vector database.
