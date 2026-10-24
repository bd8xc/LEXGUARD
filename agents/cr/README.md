# Contract Risk agent (CR)

CR predicts a risk signal for each contract clause, retrieves candidate provisions from its Indian Contract Act knowledge base, and passes the clause-specific evidence to the configured local LLM for a grounded explanation. The LLM does not receive the CL, COI, or LE results. The final report keeps those agents' findings separate and marks the analysis for human review.

See the [project README](../../README.md) for setup and run instructions.

The trained `checkpoints/best_model.pt` checkpoint is not included in this repository because it is larger than GitHub's regular file limit. Obtain it from the project maintainer or train it with `train.py`. Without that checkpoint, CR reports itself unavailable. LegalBERT scores are model outputs, not calibrated probabilities, and require human review.
