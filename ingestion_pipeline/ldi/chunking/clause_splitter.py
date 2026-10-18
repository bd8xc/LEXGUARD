"""LEGAL DOCUMENT CHUNKER (GENERIC + DYNAMIC TABLES)

Refactored into smaller modules to reduce file size without changing behavior.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .grammar import (
    ALPHA_RE,
    DEFINITION_RE,
    MAIN_RE,
    ROMAN_RE,
    SECTION_LABEL_ONLY_RE,
    SECTION_WITH_ID_RE,
    SUBNUM_RE,
    looks_like_preamble_boundary,
    looks_like_section_heading,
)
from .postprocess import (
    merge_short_heading_into_first_child,
    merge_small_children,
    pack_small_preamble,
    pack_small_siblings,
)
from .semantic_repair import semantic_cleanup
from .table_extraction import extract_tables


def split_large_chunks(
    chunks: List[Dict[str, Any]],
    max_words: int = 300,
) -> List[Dict[str, Any]]:

    output = []

    for chunk in chunks:
        text = str(chunk.get("text", "")).strip()
        words = text.split()

        # Chunk is already small enough
        if len(words) <= max_words:
            output.append(chunk)
            continue

        # Split oversized chunk
        for i in range(0, len(words), max_words):
            part_words = words[i:i + max_words]

            new_chunk = dict(chunk)
            new_chunk["text"] = " ".join(part_words)

            # Preserve original ID but distinguish parts
            new_chunk["clause_id"] = (
                f"{chunk.get('clause_id', 'chunk')}_part{i // max_words + 1}"
            )

            output.append(new_chunk)

    return output

def split_clauses(text: str) -> List[Dict[str, Any]]:
    """
    Parses the document into a tree of clauses (Section > Clause > Subclause).

    THE STACK:
    We maintain a 'stack' state to track depth.

    This allows us to assign IDs like "A1.2.b" automatically.
    """
    if not text:
        return []

    # 1. Pre-process: Clean whitespace
    raw_lines = [l.rstrip() for l in text.splitlines()]

    # 2. Extract Tables (so they don't break the text parser)
    tables, lines = extract_tables(raw_lines)

    results: List[Dict[str, Any]] = []

    # State Machine Variables
    section_name = "Document"

    # Used only to generate stable section tokens when headings are present.
    section_counter = 0
    loose_counter = 0  # for unanchored text blocks

    # Hierarchy Stack stores the rendered token at each depth
    # Supports dotted numeric clauses (e.g., 1.1, 2.3.4) plus alpha/roman bullets.
    stack = {
        "article": None,
        "main": None,
        "subnum": None,
        "subsubnum": None,
        "alpha": None,
        "roman": None,
    }

    # Text Buffer for current clause
    buffer: List[str] = []
    current_level: str = "clause"
    current_type: Optional[str] = None
    current_term: Optional[str] = None

    # --- HELPERS ---

    def build_id(current_level_parts: List[str]) -> str:
        """Constructs unique ID from current stack (e.g., '1.B.iii')."""
        parts = [p for p in current_level_parts if p]
        return ".".join(parts) if parts else ""

    def flush(level: Optional[str] = None):
        """Commits the current buffer to the results list."""
        nonlocal buffer, loose_counter, current_type, current_term, current_level
        if not buffer:
            return

        level_to_commit = level or current_level
        text_block = "\n".join(buffer).strip()
        buffer = []

        id_parts = [
            stack.get("article"),
            stack.get("main"),
            stack.get("subnum"),
            stack.get("subsubnum"),
            stack.get("alpha"),
            stack.get("roman"),
        ]
        clause_id = build_id(id_parts)
        if not clause_id:
            loose_counter += 1
            clause_id = f"P{loose_counter}"

        entry = {
            "clause_id": clause_id,
            "section": section_name,
            "level": level_to_commit,
            "text": semantic_cleanup(text_block),  # Fix broken lines before saving
        }
        if current_type:
            entry["type"] = current_type
        if current_term:
            entry["term"] = current_term
        results.append(entry)

        current_type = None
        current_term = None

    # --- MAIN PARSER LOOP ---

    for raw in lines:
        line = raw.strip()
        if not line:
            continue

        # PREAMBLE / RECITALS: split on common legal markers to avoid one giant,
        # low-coherence P* chunk before the first numbered clause.
        if stack["article"] is None and stack["main"] is None and buffer:
            if looks_like_preamble_boundary(line):
                flush()
                current_level = "clause"

        # DEFINITIONS (e.g., "Effective Date" means ...)
        m = DEFINITION_RE.match(line)
        if m:
            flush()
            current_level = "clause"
            current_type = "definition"
            current_term = m.group(1).strip()
            buffer.append(line)
            continue

        # LEVEL 1: SECTION HEADINGS (generic, non-hardcoded)
        # Examples: "ARTICLE 1 DEFINITIONS", "Exhibit B: Fee Schedule".
        if looks_like_section_heading(line) and SECTION_WITH_ID_RE.match(line):
            flush()  # Save previous work
            current_level = "clause"
            section_counter += 1
            section_name = line
            stack = {
                "article": f"S{section_counter}",
                "main": None,
                "subnum": None,
                "subsubnum": None,
                "alpha": None,
                "roman": None,
            }
            continue

        # Label-only headings (e.g., "SCHEDULE")
        # Only treat as a new section after we've entered the structured portion
        # of the document (i.e., after some numbering/sectioning has started).
        m = SECTION_LABEL_ONLY_RE.match(line)
        if m and (stack["main"] is not None or stack["article"] is not None) and looks_like_section_heading(line):
            flush()
            current_level = "clause"
            section_counter += 1
            section_name = line
            stack = {
                "article": f"S{section_counter}",
                "main": None,
                "subnum": None,
                "subsubnum": None,
                "alpha": None,
                "roman": None,
            }
            continue

        # LEVEL 2: MAIN CLAUSES ("1.", "2.1")
        # Context-aware: if we are inside an alpha item, a bare number is treated as a deeper sub-item
        if stack["alpha"] and SUBNUM_RE.match(line):
            flush()
            current_level = "subsubclause"
            m_num = SUBNUM_RE.match(line)
            # Preserve the actual numeric token (e.g., 1) -> '1') for stable IDs.
            stack["roman"] = str(m_num.group(1)).strip()
            buffer.append(m_num.group(2))
            continue

        m = MAIN_RE.match(line)
        if m:
            number_str = m.group(1)
            body = m.group(2)
            parts = [p for p in number_str.split(".") if p]

            # Dotted numeric hierarchy: 1 -> clause, 1.1 -> subclause, 1.1.1 -> subsubclause
            if len(parts) == 1:
                flush()
                current_level = "clause"
                stack["main"] = parts[0]
                stack["subnum"] = None
                stack["subsubnum"] = None
                stack["alpha"] = None
                stack["roman"] = None
            elif len(parts) == 2:
                flush()
                current_level = "subclause"
                stack["main"] = parts[0]
                stack["subnum"] = parts[1]
                stack["subsubnum"] = None
                stack["alpha"] = None
                stack["roman"] = None
            else:
                flush()
                current_level = "subsubclause"
                stack["main"] = parts[0]
                stack["subnum"] = parts[1]
                stack["subsubnum"] = ".".join(parts[2:])
                stack["alpha"] = None
                stack["roman"] = None

            buffer.append(body)
            continue

        # LEVEL 3: ALPHA SUBCLAUSES ("(a)", "b.")
        m = ALPHA_RE.match(line)
        if m:
            flush()
            current_level = "subclause"
            stack["alpha"] = str(m.group(1)).strip().upper()
            stack["roman"] = None  # Reset lower levels
            buffer.append(m.group(2))
            continue

        # LEVEL 4: ROMAN SUBSUBCLAUSES ("(i)", "ii")
        m = ROMAN_RE.match(line)
        if m:
            flush()
            current_level = "subsubclause"
            stack["roman"] = str(m.group(1)).strip().lower()
            buffer.append(m.group(2))
            continue

        # PLAIN TEXT: Append to current buffer
        buffer.append(line)

    # Final flush to catch the last clause in the document
    flush()

    results = pack_small_preamble(results)
    results = merge_short_heading_into_first_child(results)
    results = pack_small_siblings(results)
    results = merge_small_children(results)
    results = split_large_chunks(results, max_words=300)
    
    return results + tables