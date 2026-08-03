"""Shared app utilities: background worker, log capture, figure capture.

Ported from ``analysis_ui.py`` (``_SignalIO``, ``AnalysisWorker``) with a
generalised callable-based worker so the Hub can dispatch arbitrary tasks
(single analysis, batch, QC, report, script runs).
"""

from __future__ import annotations

import io
import sys
import threading
import traceback
from contextlib import contextmanager
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
# Thread-scoped stdout/stderr routing
# ---------------------------------------------------------------------------

class _ThreadRouter(io.TextIOBase):
    """Stdout replacement that routes each thread's writes to its own sink.

    ``contextlib.redirect_stdout`` rebinds ``sys.stdout`` process-wide, so a
    worker thread's redirect swallowed everything the *main* thread printed
    for as long as the task ran. This router is installed once and dispatches
    per thread instead: registered threads reach their sink, everybody else
    reaches the stream that was there before.
    """

    def __init__(self, base) -> None:
        super().__init__()
        self._base = base
        self._sinks: dict[int, Any] = {}

    def register(self, sink) -> None:
        self._sinks[threading.get_ident()] = sink

    def unregister(self) -> None:
        self._sinks.pop(threading.get_ident(), None)

    def _target(self):
        return self._sinks.get(threading.get_ident(), self._base)

    def write(self, text: str) -> int:  # noqa: D401 — io API
        target = self._target()
        if target is None:
            return len(text)
        return target.write(text) or len(text)

    def flush(self) -> None:  # noqa: D401
        target = self._target()
        if target is not None:
            try:
                target.flush()
            except Exception:  # noqa: BLE001
                pass

    def isatty(self) -> bool:  # noqa: D401
        base = self._base
        return bool(base is not None and getattr(base, "isatty", lambda: False)())


_router_lock = threading.Lock()
_routers: dict[str, _ThreadRouter] = {}
_router_depth = 0


@contextmanager
def route_output(sink) -> Iterable[None]:
    """Send *this thread's* ``print`` output to *sink* for the duration.

    Other threads keep whatever ``sys.stdout``/``sys.stderr`` they had.
    """
    global _router_depth
    with _router_lock:
        if _router_depth == 0:
            _routers["stdout"] = _ThreadRouter(sys.stdout)
            _routers["stderr"] = _ThreadRouter(sys.stderr)
            sys.stdout = _routers["stdout"]
            sys.stderr = _routers["stderr"]
        _router_depth += 1
        routers = (_routers["stdout"], _routers["stderr"])
    for router in routers:
        router.register(sink)
    try:
        yield
    finally:
        for router in routers:
            router.unregister()
        with _router_lock:
            _router_depth -= 1
            if _router_depth == 0:
                for name, router in list(_routers.items()):
                    stream = getattr(sys, name)
                    if stream is router:
                        setattr(sys, name, router._base)
                _routers.clear()


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
            with route_output(sio):
                result = self._fn()
            msg = str(result) if result is not None else f"{self.task_name} complete."
            self.finished_ok.emit(msg)
        except Exception:  # noqa: BLE001
            self.failed.emit(f"{self.task_name} failed:\n{traceback.format_exc()}")


def shutdown_worker(worker: QThread | None, *, timeout_ms: int = 30_000) -> bool:
    """Stop *worker* and block until its thread has really finished.

    Qt aborts the process (``QThread: Destroyed while thread is still
    running``) if a running thread is destroyed, which is what a window closed
    mid-task used to do. Every window that owns a worker must call this before
    it is torn down.

    The worker's signals are blocked first so a task that completes while we
    wait can't call back into a window that is on its way out. Returns True
    when the thread is finished, False if it was still running after
    *timeout_ms*.
    """
    if worker is None:
        return True
    try:
        if not worker.isRunning():
            return True
        worker.blockSignals(True)
        worker.requestInterruption()
        return bool(worker.wait(timeout_ms))
    except RuntimeError:
        # Underlying C++ object already gone — nothing left to wait for.
        return True


# ---------------------------------------------------------------------------
# Figure capture (intercept plt.show() to collect Figures)
# ---------------------------------------------------------------------------

_capture_lock = threading.Lock()
# thread ident → stack of active capture lists. Per thread so a figure lands in
# the capture that its own caller opened.
_capture_stacks: dict[int, list] = {}
_capture_depth = 0
_capture_original_show: Any = None


def _dispatch_show(*args, **kwargs):  # noqa: ANN002, ANN003
    """The single ``plt.show`` replacement installed while any capture is open."""
    import matplotlib.pyplot as plt

    stack = _capture_stacks.get(threading.get_ident())
    if stack:
        stack[-1].append(plt.gcf())
        return None
    original = _capture_original_show
    if original is not None:
        return original(*args, **kwargs)
    return None


@contextmanager
def capture_figures() -> Iterable[list]:
    """Collect every ``Figure`` passed through ``plt.show()`` while active.

    Mirrors the trick ``Experiment.save_plots`` already uses.  Use it to
    run an Arena plot method that internally calls ``plt.show()`` and hand
    the resulting figures to :meth:`PlotDock.add_figure`.

    ``plt.show`` is a module global, so a naive save/restore pair loses the
    race when two of these overlap: the second one saves the first one's hook
    as "the original" and restores it on the way out, leaving ``plt.show``
    permanently pointed at a dead capture. Here a single dispatcher is
    installed for the outermost capture and removed only when the last one
    closes, and it routes each figure to the capture opened by the calling
    thread.

    Example
    -------
    >>> with capture_figures() as figs:
    ...     arena.plot_pi_facet(cutoffs)
    >>> for fig in figs:
    ...     dock.add_figure("PI", fig)
    """
    import matplotlib.pyplot as plt

    global _capture_depth, _capture_original_show

    figures: list = []
    ident = threading.get_ident()
    with _capture_lock:
        if _capture_depth == 0:
            _capture_original_show = plt.show
            plt.show = _dispatch_show  # type: ignore[assignment]
        _capture_depth += 1
        _capture_stacks.setdefault(ident, []).append(figures)
    try:
        yield figures
    finally:
        with _capture_lock:
            stack = _capture_stacks.get(ident) or []
            if figures in stack:
                stack.remove(figures)
            if not stack:
                _capture_stacks.pop(ident, None)
            _capture_depth -= 1
            if _capture_depth == 0:
                if plt.show is _dispatch_show:
                    plt.show = _capture_original_show  # type: ignore[assignment]
                _capture_original_show = None
