"""Public API of the engine package.

Re-exports the core types defined in submodules so consumers can write
``from pitwall.engine import PacePredictor`` rather than reaching into
specific submodules.
"""

from pitwall.engine.projection import (
    Compound,
    PaceContext,
    PacePrediction,
    PacePredictor,
    UnsupportedContextError,
)

__all__ = [
    "Compound",
    "PaceContext",
    "PacePrediction",
    "PacePredictor",
    "UnsupportedContextError",
]
