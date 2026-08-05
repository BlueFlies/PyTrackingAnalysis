"""Concrete rendering backends for the report document model.

Each backend module exposes ``render(report, path) -> str``. They are imported
lazily by :mod:`pytrackinganalysis.report.render`, so importing this package
does not pull in any backend's dependencies.
"""
