"""Shared app utilities: background worker, log capture, figure capture.

Ported from ``analysis_ui.py`` (``_SignalIO``, ``AnalysisWorker``) with a
generalised callable-based worker so the Hub can dispatch arbitrary tasks
(single analysis, batch, QC, report, script runs).
"""

from __future__ import annotations

import io
import traceback
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from typing import Any, Callable, Iterable

from PyQt6.QtCore import QThread, pyqtSignal


# ---------------------------------------------------------------------------
# Live-log IO helper
# ---------------------------------------------------------------------------

class _SignalIO(io.TextIOBase):
    """Writable text stream that fires a Qt signal on every ``write()``.

    When used with :func:`contextlib.redirect_stdout` / ``redirect_stderr``
    inside a ``QThread``, Qt auto-queues the signal across the thread
    boundary, so the connected slot runs safely on the GUI thread.
    """

    def __init__(self, signal: pyqtSignal) -> None:
        super().__init__()
        self._signal = signal

    def write(self, text: str) -> int:  # noqa: D401 — io API
        if text:
            self._signal.emit(text)
        return len(text)

    def flush(self) -> None:  # noqa: D401
        pass


# ---------------------------------------------------------------------------
# Generic background worker
# ---------------------------------------------------------------------------

class TaskWorker(QThread):
    """Runs *fn* on a background thread with stdout/stderr captured.

    *fn* should return a string (shown in the success message) or ``None``.
    Exceptions are logged and surface as ``failed`` with a short message.
    """

    finished_ok = pyqtSignal(str)
    failed = pyqtSignal(str)
    log_text = pyqtSignal(str)

    def __init__(self, task_name: str, fn: Callable[[], Any]) -> None:
        super().__init__()
        self.task_name = task_name
        self._fn = fn

    def run(self) -> None:  # noqa: D401 — QThread API
        sio = _SignalIO(self.log_text)
        try:
            with redirect_stdout(sio), redirect_stderr(sio):
                result = self._fn()
            msg = str(result) if result is not None else f"{self.task_name} complete."
            self.finished_ok.emit(msg)
        except Exception:  # noqa: BLE001
            self.failed.emit(f"{self.task_name} failed:\n{traceback.format_exc()}")


# ---------------------------------------------------------------------------
# Figure capture (intercept plt.show() to collect Figures)
# ---------------------------------------------------------------------------

@contextmanager
def capture_figures() -> Iterable[list]:
    """Collect every ``Figure`` passed through ``plt.show()`` while active.

    Mirrors the trick ``Experiment.save_plots`` already uses.  Use it to
    run an Arena plot method that internally calls ``plt.show()`` and hand
    the resulting figures to :meth:`PlotDock.add_figure`.

    Example
    -------
    >>> with capture_figures() as figs:
    ...     arena.plot_pi_facet(cutoffs)
    >>> for fig in figs:
    ...     dock.add_figure("PI", fig)
    """
    import matplotlib.pyplot as plt

    figures: list = []
    original_show = plt.show

    def _capture(*_args, **_kwargs) -> None:  # noqa: ANN002, ANN003
        figures.append(plt.gcf())

    plt.show = _capture  # type: ignore[assignment]
    try:
        yield figures
    finally:
        plt.show = original_show  # type: ignore[assignment]
