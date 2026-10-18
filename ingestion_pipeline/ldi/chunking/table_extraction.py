from __future__ import annotations

from typing import List, Optional

from .grammar import (
    MAIN_RE,
    TABLE_SPLIT_RE,
    looks_like_section_heading,
)


def looks_like_table_row(line: str) -> bool:
    """
    Heuristic: Does this line look like a table row?
    Criteria:
    - Splits into at least 3 columns based on spacing/tabs
    - At least 2 cells are short (< 40 chars)
    """
    parts = TABLE_SPLIT_RE.split(line.strip())
    # Filter empty strings that might result from splitting
    parts = [p for p in parts if p.strip()]
    if len(parts) < 3:
        return False
    short_cells = sum(1 for p in parts if len(p) < 40)
    return short_cells >= 2


def extract_tables(lines: List[str]):
    """
    Extracts tables without knowing the schema beforehand.
    For each table, returns a single chunk (dict) with all rows/columns as text.

    Naming:
    - Uses the last seen non-table line as the best-effort table title.
    - Falls back to the last structural heading (Section/Main clause) if no title exists.
    """
    tables = []
    cleaned = []

    i = 0
    last_section = "Document"
    last_title: Optional[str] = None

    while i < len(lines):
        line = lines[i].strip()

        if MAIN_RE.match(line) or looks_like_section_heading(line):
            last_section = line
            last_title = None

        if looks_like_table_row(line):
            table_lines = []
            while i < len(lines) and looks_like_table_row(lines[i]):
                table_lines.append(lines[i].strip())
                i += 1

            is_valid_table = False
            rows: List[List[str]] = []
            headers: List[str] = []

            if len(table_lines) >= 3:
                for r in table_lines:
                    row_parts = [p for p in TABLE_SPLIT_RE.split(r) if p.strip()]
                    rows.append(row_parts)
                col_counts = [len(r) for r in rows]
                if col_counts and (max(col_counts) - min(col_counts) <= 1):
                    headers = [h.lower().strip().replace(" ", "_") for h in rows[0] if h.strip()]
                    if headers and all(len(h) <= 60 for h in headers):
                        is_valid_table = True

            if is_valid_table:
                # Combine all rows into a single string chunk
                table_text = "\n".join(["\t".join(row) for row in rows])
                table_name = (last_title or last_section or "Table").strip()
                tables.append(
                    {
                        "clause_id": f"TABLE_{len(tables)+1}",
                        "section": table_name,
                        "table_context": last_section,
                        "level": "table",
                        "text": table_text,
                    }
                )
            else:
                cleaned.extend(table_lines)
            continue

        # Track last non-table line as potential table title.
        if line:
            last_title = line

        cleaned.append(lines[i])
        i += 1

    return tables, cleaned
