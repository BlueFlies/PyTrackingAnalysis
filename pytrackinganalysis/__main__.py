"""Dev shortcut: ``python -m pytrackinganalysis {hub,config,qc} [args...]``.

Mirrors the ``pytrack-hub`` / ``pytrack-config`` / ``pytrack-qc`` console
scripts registered in ``pyproject.toml``; useful when the package is
installed in editable mode without the scripts on PATH.
"""

from __future__ import annotations

import sys


def main() -> int:
    if len(sys.argv) < 2:
        print(
            "usage: python -m pytrackinganalysis {hub,config,qc} [args...]",
            file=sys.stderr,
        )
        return 2

    app_name = sys.argv[1]
    # Rewrite argv so the chosen app sees a normal argv[0], argv[1:] passthrough.
    sys.argv = [f"python -m pytrackinganalysis {app_name}", *sys.argv[2:]]

    if app_name == "hub":
        from .apps.hub import main as app_main
    elif app_name == "config":
        from .apps.config_editor import main as app_main
    elif app_name == "qc":
        from .apps.qc_viewer import main as app_main
    else:
        print(f"unknown app: {app_name!r} (expected hub|config|qc)", file=sys.stderr)
        return 2

    return int(app_main() or 0)


if __name__ == "__main__":
    raise SystemExit(main())
