"""Backend dispatcher for rendering a :class:`~pytrackinganalysis.report.model.Report`.

The analysis core calls :func:`render` and names a backend by string; it never
imports a rendering library directly. Add a new engine by writing a module with
a ``render(report, path)`` function and registering it in ``_BACKENDS``.
"""

from __future__ import annotations

from . import model as m

# name -> "module:function" (imported lazily so an unused backend's heavy
# dependency is never imported).
_BACKENDS = {
    "reportlab": "pytrackinganalysis.report.backends.reportlab_backend:render",
    # Future engines slot in here over the same document model, e.g.:
    #   "markdown": "pytrackinganalysis.report.backends.markdown_backend:render",
    #   "latex":    "pytrackinganalysis.report.backends.latex_backend:render",
}


def available_backends() -> list[str]:
    """Names of the registered rendering backends."""
    return sorted(_BACKENDS)


def render(report: m.Report, path: str, backend: str = "reportlab") -> str:
    """Render *report* to *path* using the named *backend*; returns *path*."""
    import importlib

    try:
        target = _BACKENDS[backend]
    except KeyError:
        raise ValueError(
            f"Unknown report backend {backend!r}. "
            f"Available: {', '.join(available_backends())}"
        ) from None
    module_name, func_name = target.split(":")
    module = importlib.import_module(module_name)
    return getattr(module, func_name)(report, path)
