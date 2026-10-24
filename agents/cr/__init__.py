"""Contract risk agent.

Keep the legacy top-level imports (``models``, ``processing``, and related
packages) working when the analyzer is imported as ``agents.cr``.
"""

from pathlib import Path
import sys

_CR_ROOT = str(Path(__file__).resolve().parent)
if _CR_ROOT not in sys.path:
    sys.path.insert(0, _CR_ROOT)
