from __future__ import annotations

import re

# ==============================================================================
# REGEX GRAMMAR (STRUCTURE + TABLES)
# ==============================================================================

# HIERARCHY PATTERNS
# These regexes define the "skeleton" of the document.

# Generic section heading detection (non-hardcoded):
# 1) Label + identifier (safe): "ARTICLE 1", "Schedule A", "Section IV".
# 2) Label-only (cautious): "SCHEDULE" (the parser applies extra guards).
SECTION_WITH_ID_RE = re.compile(
	r"^(?P<label>[A-Z][A-Z0-9&/\\\-]{2,})[\s\-–—:]+(?P<id>[0-9IVXLCDM]+|[A-Z])\b",
	re.I,
)
SECTION_LABEL_ONLY_RE = re.compile(r"^(?P<label>[A-Z][A-Z0-9&/\\\-]{2,})\s*$", re.I)
MAIN_RE = re.compile(r"^(\d+(?:\.\d+)*)[\.\)]?\s+(.*)")

# Require an explicit bullet marker (')' or '.') so normal sentences like
# "a minimum of ..." don't get misclassified as subclauses.
ALPHA_RE = re.compile(r"^\(?([a-z])[\)\.]\s+(.*)", re.I)
ROMAN_RE = re.compile(r"^\(?([ivxlcdm]+)[\)\.]\s+(.*)", re.I)

# Numeric bullets inside subclauses (e.g., 1) Labor ... under a lettered item)
# Important: require a closing ')' so we don't misclassify top-level clauses like
# '3. Compensation and Benefits' as a nested bullet.
SUBNUM_RE = re.compile(r"^\(?([0-9]+)\)\s+(.*)")

# Definitions (e.g., "Effective Date" means ...)
DEFINITION_RE = re.compile(r'^"([^"]+)"\s+(means|shall mean|refers to)', re.I)

# GENERIC TABLE DETECTION
# Matches lines containing tabs OR sequences of 3+ spaces.
# Why 3 spaces? It's a common heuristic for visually aligned columns in plain text.
TABLE_SPLIT_RE = re.compile(r"\t+|\s{3,}")


def _uppercase_ratio(s: str) -> float:
	letters = [ch for ch in s if ch.isalpha()]
	if not letters:
		return 0.0
	upper = sum(1 for ch in letters if ch.isupper())
	return upper / max(1, len(letters))


def looks_like_preamble_boundary(line: str) -> bool:
	"""Heuristic for splitting preambles without hardcoded keyword lists.

	We treat short, heading-like, mostly-uppercase lines (e.g., "WHEREAS") as
	safe boundaries between preamble blocks.
	"""
	s = str(line or "").strip()
	if not s:
		return False
	if MAIN_RE.match(s) or DEFINITION_RE.match(s):
		return False

	# Avoid splitting on normal sentences.
	if s.endswith("."):
		return False

	words = s.split()
	if len(words) > 8:
		return False

	# Mostly-uppercase and short => likely a marker line.
	if len(s) <= 80 and _uppercase_ratio(s) >= 0.85:
		return True

	return False


def looks_like_section_heading(line: str) -> bool:
	"""Heuristic section-heading detector (non-hardcoded).

	Goal: identify real structural headings (e.g., "ARTICLE 1 DEFINITIONS",
	"Exhibit B: Fee Schedule") while avoiding false positives such as
	page headers ("Page 1") or normal sentences.
	"""
	s = str(line or "").strip()
	if not s:
		return False

	# Sentences (or continuations) are unlikely to be headings.
	if s.endswith("."):
		return False

	# Numeric clauses/definitions are handled elsewhere.
	if MAIN_RE.match(s) or DEFINITION_RE.match(s):
		return False

	# Accept label-only headings only if they are fully uppercased.
	if s.isupper() and SECTION_LABEL_ONLY_RE.match(s):
		return True

	if not SECTION_WITH_ID_RE.match(s):
		return False

	# Require some heading-like signal.
	# - ALL CAPS headings are common in contracts.
	# - Colon/dash separators are common for "Label ID: Title" forms.
	has_separator = (":" in s) or ("-" in s) or ("—" in s) or ("–" in s)
	if s.isupper() or has_separator:
		return True

	# Otherwise, be conservative (avoid matching "Page 1"-style lines).
	return False
