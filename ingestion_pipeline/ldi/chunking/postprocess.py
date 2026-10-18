from __future__ import annotations

from typing import Any, Dict, List, Optional


def _parent_clause_id(clause_id: str) -> Optional[str]:
    parts = [p for p in str(clause_id).split(".") if p]
    if len(parts) <= 1:
        return None
    return ".".join(parts[:-1])


def merge_small_children(
    items: List[Dict[str, Any]],
    *,
    max_chunk_chars: int = 2500,
    child_max_chars: int = 800,
) -> List[Dict[str, Any]]:
    """Merge small subclauses into their nearest existing parent clause.

    This reduces noisy micro-chunks (e.g., many 1–2 line bullets) while keeping
    each merged chunk under a safe size limit for LLM consumption.

    Notes:
    - Only merges levels below a clause (subclause/subsubclause) and only when
      the child text is short.
    - Preserves traceability by prefixing merged lines with the child clause_id.
    """
    if not items:
        return items

    id_to_index: Dict[str, int] = {}
    for idx, entry in enumerate(items):
        cid = entry.get("clause_id")
        if isinstance(cid, str) and cid:
            id_to_index[cid] = idx

    keep = [True] * len(items)

    def depth(cid: str) -> int:
        return str(cid).count(".")

    indices = list(range(len(items)))
    indices.sort(key=lambda i: depth(items[i].get("clause_id", "")), reverse=True)

    for idx in indices:
        if not keep[idx]:
            continue

        entry = items[idx]
        level = str(entry.get("level") or "")
        if level not in {"subclause", "subsubclause"}:
            continue

        text = str(entry.get("text") or "").strip()
        if not text or len(text) > child_max_chars:
            continue

        clause_id = str(entry.get("clause_id") or "").strip()
        if not clause_id:
            continue

        parent_id = _parent_clause_id(clause_id)
        parent_idx: Optional[int] = None
        while parent_id:
            candidate = id_to_index.get(parent_id)
            if candidate is not None and keep[candidate]:
                parent_idx = candidate
                break
            parent_id = _parent_clause_id(parent_id)

        if parent_idx is None:
            continue

        parent = items[parent_idx]
        parent_text = str(parent.get("text") or "").strip()
        if not parent_text:
            parent_text = ""

        merged_line = f"- [{clause_id}] {text.replace(chr(10), ' ')}"
        new_text = (parent_text + "\n" + merged_line).strip() if parent_text else merged_line

        if len(new_text) > max_chunk_chars:
            continue

        parent["text"] = new_text
        keep[idx] = False

    return [items[i] for i in range(len(items)) if keep[i]]


def merge_short_heading_into_first_child(
    items: List[Dict[str, Any]],
    *,
    max_chunk_chars: int = 2500,
    heading_max_chars: int = 140,
) -> List[Dict[str, Any]]:
    """If a parent is just a short heading, prepend it into its first child.

    Common pattern: "2. Governance" (short) followed by "2.1 ..." etc.
    Keeping the heading as its own chunk is rarely helpful.
    """
    if not items:
        return items

    keep = [True] * len(items)
    id_to_indices: Dict[str, List[int]] = {}
    for idx, entry in enumerate(items):
        cid = entry.get("clause_id")
        if isinstance(cid, str) and cid:
            id_to_indices.setdefault(cid, [])

    # Build child lists by scanning in original order
    for idx, entry in enumerate(items):
        cid = entry.get("clause_id")
        if not isinstance(cid, str) or not cid:
            continue
        parent = _parent_clause_id(cid)
        if parent:
            id_to_indices.setdefault(parent, []).append(idx)

    for parent_idx, parent in enumerate(items):
        if not keep[parent_idx]:
            continue

        if str(parent.get("level") or "") != "clause":
            continue

        parent_text = str(parent.get("text") or "").strip()
        if not parent_text:
            continue

        # Heuristic: short, single-line headings
        if len(parent_text) > heading_max_chars or "\n" in parent_text:
            continue

        parent_id = parent.get("clause_id")
        if not isinstance(parent_id, str) or not parent_id:
            continue

        child_indices = [i for i in id_to_indices.get(parent_id, []) if keep[i]]
        if not child_indices:
            continue

        first_child_idx = child_indices[0]
        child = items[first_child_idx]
        child_text = str(child.get("text") or "").strip()
        if not child_text:
            continue

        new_text = f"{parent_text}\n{child_text}"
        if len(new_text) > max_chunk_chars:
            continue

        child["text"] = new_text
        keep[parent_idx] = False

    return [items[i] for i in range(len(items)) if keep[i]]


def pack_small_preamble(
    items: List[Dict[str, Any]],
    *,
    min_words: int = 35,
    max_chunk_chars: int = 2500,
) -> List[Dict[str, Any]]:
    """Merge tiny P* preamble chunks into fewer, larger chunks.

    This keeps preambles from dragging down average chunk size while staying
    strictly within the preamble region.
    """
    if not items:
        return items

    out: List[Dict[str, Any]] = []
    i = 0
    while i < len(items):
        current = items[i]
        cid = str(current.get("clause_id") or "")
        if not cid.startswith("P"):
            out.append(current)
            i += 1
            continue

        text = str(current.get("text") or "").strip()
        if not text:
            out.append(current)
            i += 1
            continue

        merged = dict(current)
        while (
            len(text.split()) < min_words
            and i + 1 < len(items)
            and str(items[i + 1].get("clause_id") or "").startswith("P")
            and items[i + 1].get("section") == merged.get("section")
        ):
            nxt = items[i + 1]
            nxt_text = str(nxt.get("text") or "").strip()
            if not nxt_text:
                i += 1
                continue

            candidate = (text + "\n" + nxt_text).strip()
            if len(candidate) > max_chunk_chars:
                break
            text = candidate
            i += 1

        merged["text"] = text
        out.append(merged)
        i += 1

    return out


def pack_small_siblings(
    items: List[Dict[str, Any]],
    *,
    min_words: int = 35,
    max_chunk_chars: int = 2500,
    sibling_max_words: int = 140,
) -> List[Dict[str, Any]]:
    """Pack tiny sibling bullets under the same parent into fewer chunks.

    Example: 2.A, 2.B, 2.C ... (all under 2) may be too small individually.
    This merges adjacent siblings while preserving traceability by prefixing
    merged lines with the merged-in clause_id.
    """
    if not items:
        return items

    out: List[Dict[str, Any]] = []
    i = 0
    while i < len(items):
        current = items[i]
        level = str(current.get("level") or "")
        cid = str(current.get("clause_id") or "")
        text = str(current.get("text") or "").strip()

        if level not in {"subclause", "subsubclause"} or not cid or not text:
            out.append(current)
            i += 1
            continue

        parent_id = _parent_clause_id(cid)
        merged = dict(current)
        merged_text = text

        # Merge forward while: same parent, same level, and current chunk is still small.
        while i + 1 < len(items):
            if len(merged_text.split()) >= min_words:
                break

            nxt = items[i + 1]
            nxt_level = str(nxt.get("level") or "")
            nxt_cid = str(nxt.get("clause_id") or "")
            if nxt_level != level:
                break
            if _parent_clause_id(nxt_cid) != parent_id:
                break

            nxt_text = str(nxt.get("text") or "").strip()
            if not nxt_text:
                i += 1
                continue

            if len(nxt_text.split()) > sibling_max_words:
                break

            merged_line = f"- [{nxt_cid}] {nxt_text.replace(chr(10), ' ')}"
            candidate = (merged_text + "\n" + merged_line).strip()
            if len(candidate) > max_chunk_chars:
                break

            merged_text = candidate
            i += 1

        merged["text"] = merged_text
        out.append(merged)
        i += 1

    return out
