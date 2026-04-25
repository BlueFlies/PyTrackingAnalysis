"""PyTrackingAnalysis package.

Submodules (Arena, Tracker, Experiment, …) are loaded **lazily** on first
attribute access so that the GUI apps can call ``matplotlib.use("Agg")``
*before* pyplot is imported through these submodules. Eagerly importing them
here forced a Qt-based pyplot backend onto worker threads and aborted the
process during ``Run Analysis``.

``from pytrackinganalysis import Experiment`` still works for notebooks and
scripts — Python's PEP-562 ``__getattr__`` turns the access into a normal
``import pytrackinganalysis.Experiment``.
"""
from __future__ import annotations

import importlib

__all__ = [
    "Arena",
    "Counter",
    "Experiment",
    "ExperimentalDesign",
    "PairwiseInteractionCounter",
    "PairwiseInteractionTracker",
    "Parameters",
    "SpecialFunctions",
    "Tracker",
    "TwoChoiceCounter",
    "TwoChoiceTracker",
    "XChoiceTracker",
]


def __getattr__(name):
    if name in __all__:
        module = importlib.import_module(f".{name}", __name__)
        globals()[name] = module
        return module
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return sorted(list(globals().keys()) + __all__)
