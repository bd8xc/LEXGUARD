"""Conflict of Interest analysis backed by an evidence graph."""

from .conflict_agent import ConflictOfInterestAgent
from .domain import ConflictReport, Edge

__all__ = ["ConflictOfInterestAgent", "ConflictReport", "Edge"]
