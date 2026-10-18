# CL detectors

Independent detectors for regex identifiers, PII, sensitive personal data, confidential business content, processing activity, and spaCy NER context. `patterns.py` and `dictionaries.py` hold shared detection vocabularies. NER availability affects context detection; deterministic detectors can still run without the model.
