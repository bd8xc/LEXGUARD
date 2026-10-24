"""Minimal LangGraph-compatible adapter for the Litigation Exposure Agent."""

from __future__ import annotations

from .litigation_agent import LexState, LitigationExposureAgent


def litigation_agent_node(state: LexState) -> LexState:
    """Run Agent 3 after upstream agents have populated ``state``."""
    return LitigationExposureAgent().run(state)
