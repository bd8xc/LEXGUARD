"""
ClauseRetriever: Semantic search over embedded legal clauses in ChromaDB.
"""
from typing import List, Dict, Any
import os
import re
from pathlib import Path
from sentence_transformers import SentenceTransformer
import chromadb
from chromadb.config import Settings

class ClauseRetriever:
    """
    Retrieves legal clauses/chunks from Chroma using semantic embeddings.

    Core behavior:
    - Runs vector similarity search against the clause collection.
    - Optionally prioritizes table chunks for table-like questions.
    - Detects document names in the query and boosts matches from that file.
    """
    def __init__(self, model_name: str = "all-MiniLM-L6-v2", persist_directory: str = "./chroma", collection_name: str = "clauses"):
        if not os.path.isabs(persist_directory):
            repository_root = Path(__file__).resolve().parents[2]
            persist_directory = str(repository_root / persist_directory)
        # Encoder converts queries into vectors compatible with stored clause embeddings.
        self._model = SentenceTransformer(model_name)
        # Persistent Chroma client lets search survive process restarts.
        self._client = chromadb.PersistentClient(path=persist_directory, settings=Settings(allow_reset=True))
        self._collection = self._client.get_or_create_collection(collection_name)
        # Cached once, reused on subsequent queries for faster doc-name matching.
        self._known_file_names = None

    def search(self, query: str, k: int = 5) -> List[Dict[str, Any]]:
        """
        Main retrieval entry point.

        Flow:
        1) Validate query and collection state.
        2) Encode query into an embedding.
        3) Pull a larger candidate set to allow re-ranking.
        4) Re-rank by mentioned document (if detected).
        5) Return top-k formatted results.

        Args:
            query (str): Query text.
            k (int): Number of results to return.
        Returns:
            List[Dict]: List of matching clause/table dicts with metadata and score.
        """
        if not query:
            return []

        # Empty DB guard
        try:
            total_docs = self._collection.count()
            if total_docs == 0:
                return []
        except Exception:
            # If count() isn't available for any reason, just proceed.
            total_docs = 0

        # Embed the query once and reuse for all query paths.
        query_emb = self._model.encode([query], show_progress_bar=False, convert_to_numpy=True)[0]
        # If user names a document, we will boost chunks from that file.
        mentioned_doc = self._extract_mentioned_document(query)
        # Pull more than k so reranking has enough options to promote doc matches.
        candidate_k = max(k * 5, 25)
        if total_docs:
            candidate_k = min(candidate_k, total_docs)

        results = None
        try:
            # For explicit table intent, query only table chunks first.
            if self._should_prioritize_tables(query):
                results = self._collection.query(
                    query_embeddings=[query_emb.tolist()],
                    n_results=candidate_k,
                    where={"level": "table"},
                )
                # If no table matches, fall back to full-corpus search.
                if not results.get("ids") or not results.get("ids", [[]])[0]:
                    results = None

            # Default path: search full corpus.
            if results is None:
                results = self._collection.query(
                    query_embeddings=[query_emb.tolist()],
                    n_results=candidate_k,
                )
        except Exception:
            # Retrieval should fail safe and return empty results to caller.
            return []
        matches = []
        ids = results.get("ids", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        documents = results.get("documents", [[]])[0]
        scores = results.get("distances", [[]])[0] if "distances" in results else [None]*len(ids)
        for i in range(len(ids)):
            meta = metadatas[i] if i < len(metadatas) else {}
            text = documents[i] if i < len(documents) else None
            # Use formatting for table chunks everywhere
            if meta.get("level") == "table" and text:
                text = self._format_table_text(text)
            match = {
                "clause_id": meta.get("clause_id"),
                "section": meta.get("section"),
                "level": meta.get("level"),
                "file_name": meta.get("file_name"),
                "text": text,
                "score": float(scores[i]) if scores and i < len(scores) and scores[i] is not None else None
            }
            matches.append(match)

        # Promote chunks from user-mentioned file before truncating to k.
        if mentioned_doc:
            matches = self._rerank_with_doc_priority(matches, mentioned_doc)

        return matches[:k]

    def _rerank_with_doc_priority(self, matches: List[Dict[str, Any]], mentioned_doc: str) -> List[Dict[str, Any]]:
        """
        Re-rank candidates so chunks from the mentioned document come first.

        Sort order:
        - Group 1: rows whose file_name matches mentioned_doc
        - Group 2: all other rows
        - Within each group: lower distance score first (better relevance)
        """
        def sort_key(pair):
            idx, item = pair
            file_name = str(item.get("file_name") or "")
            is_doc_match = self._is_document_match(file_name, mentioned_doc)
            score = item.get("score")
            if score is None:
                score = float("inf")
            return (0 if is_doc_match else 1, score, idx)

        ranked_pairs = sorted(enumerate(matches), key=sort_key)
        return [item for _, item in ranked_pairs]

    def _extract_mentioned_document(self, query: str) -> str:
        """
        Infer which indexed document the user is referring to.

        Strategy:
        - Try direct substring match (exact-ish mention of file name/stem).
        - Else use token overlap scoring for partial mentions (for example, acronyms).
        - Return best match only if confidence crosses threshold.
        """
        normalized_query = self._normalize_text(query)
        if not normalized_query:
            return ""

        query_tokens = self._tokenize(normalized_query)
        if not query_tokens:
            return ""

        # Honor explicit hints first (for example: "in the COE document").
        hinted_doc = self._extract_explicit_document_hint(normalized_query)
        if hinted_doc:
            return hinted_doc

        best_doc = ""
        best_score = 0.0
        best_overlap_count = 0
        best_max_overlap_token_len = 0
        second_best_score = 0.0
        for file_name in self._get_known_file_names():
            raw_name = str(file_name)
            base_name = os.path.basename(raw_name)
            stem, _ = os.path.splitext(base_name)
            candidates = [base_name, stem, raw_name]
            for candidate in candidates:
                normalized_candidate = self._normalize_text(candidate)
                if normalized_candidate and normalized_candidate in normalized_query:
                    return raw_name
                candidate_tokens = self._tokenize(normalized_candidate)
                score, overlap_count, max_overlap_token_len = self._document_mention_score(query_tokens, candidate_tokens)
                if score > best_score:
                    second_best_score = best_score
                    best_score = score
                    best_doc = raw_name
                    best_overlap_count = overlap_count
                    best_max_overlap_token_len = max_overlap_token_len
                elif score > second_best_score:
                    second_best_score = score

        # Reject weak/ambiguous matches: require confidence and clear separation.
        score_margin = best_score - second_best_score
        has_min_overlap_signal = best_overlap_count >= 2 or (
            best_overlap_count == 1 and best_max_overlap_token_len >= 3
        )
        is_confident = best_score >= 0.34 and score_margin >= 0.08
        return best_doc if has_min_overlap_signal and is_confident else ""

    def _extract_explicit_document_hint(self, normalized_query: str) -> str:
        """Extract and resolve explicit 'X document/file/pdf' phrases from user query."""
        patterns = [
            r"\b(?:in|from|of)\s+the\s+([a-z0-9\- ]{2,50}?)\s+(?:document|file|pdf)\b",
            r"\b([a-z0-9\- ]{2,50}?)\s+(?:document|file|pdf)\b",
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, normalized_query):
                hinted_phrase = self._normalize_text(match.group(1))
                hinted_tokens = self._tokenize(hinted_phrase)
                if not hinted_tokens:
                    continue

                best_doc = ""
                best_score = 0.0
                for file_name in self._get_known_file_names():
                    raw_name = str(file_name)
                    base_name = os.path.basename(raw_name)
                    stem, _ = os.path.splitext(base_name)
                    candidates = [base_name, stem, raw_name]
                    for candidate in candidates:
                        candidate_tokens = self._tokenize(self._normalize_text(candidate))
                        score, overlap_count, max_overlap_token_len = self._document_mention_score(
                            hinted_tokens,
                            candidate_tokens,
                        )
                        if overlap_count >= 1 and max_overlap_token_len >= 3 and score > best_score:
                            best_score = score
                            best_doc = raw_name

                if best_doc and best_score >= 0.40:
                    return best_doc

        return ""

    def _document_mention_score(self, query_tokens: List[str], doc_tokens: List[str]) -> tuple[float, int, int]:
        """
        Compute confidence that query tokens reference a specific document.

        Higher value means stronger evidence that the query mentions the document.
        """
        if not query_tokens or not doc_tokens:
            return 0.0, 0, 0

        q = set(query_tokens)
        d = set(doc_tokens)
        overlap = q.intersection(d)
        if not overlap:
            return 0.0, 0, 0

        # Reward overlapping terms while avoiding false positives from common words.
        recall = len(overlap) / len(d)
        precision = len(overlap) / len(q)
        length_bonus = max((len(tok) for tok in overlap), default=0) / 10.0
        score = (0.55 * recall) + (0.35 * precision) + (0.10 * min(length_bonus, 1.0))
        return score, len(overlap), max((len(tok) for tok in overlap), default=0)

    def _get_known_file_names(self) -> List[str]:
        """
        Load unique file names from metadata and cache them in memory.

        Cached list avoids repeated full metadata scans on every query.
        """
        if self._known_file_names is not None:
            return self._known_file_names

        file_names = set()
        try:
            total = self._collection.count()
            batch_size = 1000
            for offset in range(0, total, batch_size):
                chunk = self._collection.get(limit=batch_size, offset=offset, include=["metadatas"])
                for meta in chunk.get("metadatas", []):
                    if isinstance(meta, dict):
                        name = meta.get("file_name")
                        if name:
                            file_names.add(str(name))
        except Exception:
            pass

        self._known_file_names = sorted(file_names, key=len, reverse=True)
        return self._known_file_names

    def _is_document_match(self, result_file_name: str, mentioned_doc: str) -> bool:
        """Check whether a result row belongs to the inferred mentioned document."""
        result_norm = self._normalize_text(result_file_name)
        mentioned_norm = self._normalize_text(mentioned_doc)
        if not result_norm or not mentioned_norm:
            return False
        return mentioned_norm in result_norm or result_norm in mentioned_norm

    def _normalize_text(self, value: str) -> str:
        """Lowercase and normalize non-alphanumeric separators for robust matching."""
        value = (value or "").lower()
        value = re.sub(r"[^a-z0-9]+", " ", value)
        return " ".join(value.split())

    def _tokenize(self, value: str) -> List[str]:
        """Split normalized text into informative tokens for mention matching."""
        stopwords = {
            "the", "a", "an", "and", "or", "of", "in", "to", "for", "on", "at",
            "with", "by", "from", "is", "are", "was", "were", "be", "this", "that",
            "document", "contract", "agreement", "file", "pdf", "docx"
        }
        return [tok for tok in value.split() if len(tok) >= 2 and tok not in stopwords]

    def _should_prioritize_tables(self, query: str) -> bool:
        """Return True when query intent is table-centric, enabling table-first retrieval."""
        q = query.lower()
        return "table" in q or "tabular" in q or "rows" in q or "columns" in q

    def _format_table_text(self, table_text: str) -> str:
        """
        Format extracted table text for readable display in API responses.

        Stored rows are tab-delimited; we render them as pipe-separated columns.
        """
        lines = table_text.split("\n")
        formatted = "\n".join([" | ".join(row.split("\t")) for row in lines])
        return formatted
