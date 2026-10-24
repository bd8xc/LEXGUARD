"""
Pipeline for semantic search over legal clauses.
"""
from typing import List, Dict, Any
from .retriever import ClauseRetriever

def search_clauses(query: str, k: int = 5) -> List[Dict[str, Any]]:
    """
    Search for most similar clauses to the query.
    Args:
        query (str): Query text.
        k (int): Number of results to return.
    Returns:
        List[Dict]: List of matching clause dicts.
    """
    retriever = ClauseRetriever()
    return retriever.search(query, k)
