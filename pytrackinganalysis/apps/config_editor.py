"""Config Editor — the standalone editor for ``tracking_config.yaml``.

Wraps the form-based tab widgets (:mod:`._config_tabs`) in a pyflic-style
chrome: :class:`TopBar` with Open/Save/Save-As and a theme toggle, a
three-tab :class:`QTabWidget` hosted inside :class:`Card` panels, and a
live YAML-preview Card at the bottom.  The Script Editor (Phase 4) opens
from the File menu / toolbar as a non-modal child window.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

import yaml
from PyQt6.QtCore import QSize, QTimer
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..ui import (
    ActionButton,
    Card,
    Category,
    TopBar,
    app_icon,
    apply_theme,
    icon,
    resolved_mode,
)
from ..ui import settings as ui_settings
from ._config_tabs import CountingRegionsTab, GlobalTab, TrackingRegionsTab


class ConfigEditorWindow(QMainWindow):
    """Main window for the Config Editor app."""

    def __init__(self, initial_path: str | None = None) -> None:
        super().__init__()
        self.resize(1200, 820)
        self._current_path: Optional[Path] = None
        self._disk_text: str = ""  # yaml serialized at last load/save
        # The document as loaded. Saving edits only the sections this editor
        # owns, so keys it does not display (scripts:, anything hand-added)
        # survive a load/save round trip.
        self._loaded_config: dict = {}

        self._build_ui()

        # Resolve initial path: explicit arg, cwd, or package default.
        if initial_path:
            candidate = Path(initial_path).expanduser().resolve()
            if candidate.is_dir():
                candidate = candidate / "tracking_config.yaml"
            if candidate.exists():
                self._load_path(candidate)
                return

        for cwd_candidate in (
            Path.cwd() / "tracking_config.yaml",
            Path(__file__).resolve().parents[2] / "tracking_config.yaml",
        ):
            if cwd_candidate.exists():
                self._load_path(cwd_candidate)
                return

        self._set_title(None)

    # ==================================================================
    # UI construction
    # ==================================================================

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Top bar ─────────────────────────────────────────────────────
        self._top_bar = TopBar("Config Editor")
        btn_open = QToolButton()
        btn_open.setIcon(icon("open"))
        btn_open.setIconSize(QSize(18, 18))
        btn_open.setAutoRaise(True)
        btn_open.setToolTip("Open a YAML config")
        btn_open.clicked.connect(self._open_dialog)
        self._top_bar.add_right(btn_open)

        btn_save = QToolButton()
        btn_save.setIcon(icon("save"))
        btn_save.setIconSize(QSize(18, 18))
        btn_save.setAutoRaise(True)
        btn_save.setToolTip("Save")
        btn_save.clicked.connect(self._save)
        self._top_bar.add_right(btn_save)

        btn_save_as = QToolButton()
        btn_save_as.setIcon(icon("save_as"))
        btn_save_as.setIconSize(QSize(18, 18))
        btn_save_as.setAutoRaise(True)
        btn_save_as.setToolTip("Save as…")
        btn_save_as.clicked.connect(self._save_as)
        self._top_bar.add_right(btn_save_as)

        btn_script = QToolButton()
        btn_script.setIcon(icon("scripts", category=Category.SCRIPTS))
        btn_script.setIconSize(QSize(18, 18))
        btn_script.setAutoRaise(True)
        btn_script.setToolTip("Open Script Editor (Phase 4)")
        btn_script.clicked.connect(self._launch_script_editor)
        self._top_bar.add_right(btn_script)

        self._btn_theme = QToolButton()
        self._btn_theme.setIcon(
            icon("theme_dark" if resolved_mode() == "light" else "theme_light")
        )
        self._btn_theme.setIconSize(QSize(18, 18))
        self._btn_theme.setAutoRaise(True)
        self._btn_theme.setToolTip("Toggle light / dark theme")
        self._btn_theme.clicked.connect(self._toggle_theme)
        self._top_bar.add_right(self._btn_theme)
        outer.addWidget(self._top_bar)

        # ── File path bar ───────────────────────────────────────────────
        path_bar = QWidget()
        pbl = QHBoxLayout(path_bar)
        pbl.setContentsMargins(16, 8, 16, 8)
        pbl.setSpacing(8)
        self._path_label = QLabel("No file loaded")
        self._path_label.setStyleSheet("color: palette(text); font-weight: 500;")
        self._dirty_label = QLabel("")
        self._dirty_label.setStyleSheet("color: #f59e0b; font-weight: 600;")
        pbl.addWidget(self._path_label, 1)
        pbl.addWidget(self._dirty_label)
        outer.addWidget(path_bar)

        # Tabs (wrapped in a Card)
        tabs_card = Card(
            "Configuration",
            category=Category.NEUTRAL,
            subtitle="Edit the global settings, tracking regions, and counting regions.",
            icon_name="config",
        )
        self._tabs = QTabWidget()
        self._global_tab = GlobalTab()
        self._tracking_tab = TrackingRegionsTab(self._global_tab)
        self._counting_tab = CountingRegionsTab()
        self._tabs.addTab(self._global_tab, "Global")
        self._tabs.addTab(self._tracking_tab, "Tracking regions")
        self._tabs.addTab(self._counting_tab, "Counting regions")
        tabs_card.add_body(self._tabs)
        outer.addWidget(tabs_card, 1)

        # Poll the form vs. disk so the "unsaved changes" indicator stays live.
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setInterval(400)
        self._refresh_timer.timeout.connect(self._refresh_dirty)
        self._refresh_timer.start()

    # ==================================================================
    # Load / save
    # ==================================================================

    def _open_dialog(self) -> None:
        start = str(self._current_path.parent) if self._current_path else os.getcwd()
        path, _ = QFileDialog.getOpenFileName(
            self, "Open config", start, "YAML files (*.yaml *.yml);;All files (*)"
        )
        if path:
            self._load_path(Path(path))

    def _load_path(self, path: Path) -> None:
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
                config = yaml.safe_load(text) or {}
        except Exception as err:  # noqa: BLE001
            QMessageBox.critical(self, "Error", f"Could not load file:\n{err}")
            return
        self._loaded_config = config if isinstance(config, dict) else {}
        self._global_tab.load(config)
        self._tracking_tab.load(config)
        self._counting_tab.load(config)
        self._current_path = path
        self._disk_text = yaml.safe_dump(config, default_flow_style=False, sort_keys=False)
        self._set_title(path)
        self._refresh_dirty()
        ui_settings.add_recent_project(path.parent)

    def _save(self) -> None:
        if self._current_path is None:
            self._save_as()
            return
        self._write(self._current_path)

    def _save_as(self) -> None:
        start = str(self._current_path) if self._current_path else "tracking_config.yaml"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save config", start, "YAML files (*.yaml *.yml);;All files (*)"
        )
        if path:
            self._write(Path(path))
            self._current_path = Path(path)
            self._set_title(self._current_path)

    def _write(self, path: Path) -> None:
        errors = self._global_tab.validation_errors()
        if errors:
            # Writing anyway would drop the offending fields from the file and
            # leave the analysis running on rig defaults without telling anyone.
            QMessageBox.warning(
                self,
                "Fix these fields first",
                "The config was not saved:\n\n  • " + "\n  • ".join(errors),
            )
            return

        config = self._dump_config()
        try:
            with open(path, "w", encoding="utf-8") as f:
                yaml.dump(
                    config, f,
                    default_flow_style=False, allow_unicode=True, sort_keys=False,
                )
        except Exception as err:  # noqa: BLE001
            QMessageBox.critical(self, "Error", f"Could not save file:\n{err}")
            return
        self._disk_text = yaml.safe_dump(config, default_flow_style=False, sort_keys=False)
        self._refresh_dirty()
        QMessageBox.information(self, "Saved", f"Config saved to:\n{path}")

    def _dump_config(self) -> dict:
        """The document to write: the loaded YAML with this editor's sections replaced.

        Rebuilding the document from the three visible tabs alone would drop every
        top-level key the editor does not render — ``scripts:`` most importantly —
        and any hand-added key inside ``global:``.
        """
        config: dict = dict(self._loaded_config)

        dumped_global = self._global_tab.dump().get("global", {})
        owned = self._global_tab.owned_keys()
        # Walk the loaded keys first so the on-disk key order survives a save.
        merged_global: dict = {}
        for key, value in (config.get("global") or {}).items():
            if key in dumped_global:
                merged_global[key] = dumped_global[key]
            elif key not in owned:
                merged_global[key] = value  # not ours to touch — keep verbatim
            # An owned key the tab no longer produces was cleared by the user.
        for key, value in dumped_global.items():
            merged_global.setdefault(key, value)
        config["global"] = merged_global

        config.update(self._tracking_tab.dump())
        config.update(self._counting_tab.dump())
        return config

    # ==================================================================
    # Dirty indicator
    # ==================================================================

    def _refresh_dirty(self) -> None:
        try:
            text = yaml.safe_dump(
                self._dump_config(), default_flow_style=False, sort_keys=False
            )
        except Exception:  # noqa: BLE001
            return
        dirty = text != self._disk_text
        self._dirty_label.setText("●  unsaved changes" if dirty else "")

    def _set_title(self, path: Path | None) -> None:
        if path is None:
            self.setWindowTitle("PyTrackingAnalysis — Config Editor")
            self._path_label.setText("No file loaded")
            self._path_label.setToolTip("")
        else:
            self.setWindowTitle(f"PyTrackingAnalysis — Config Editor — {path.name}")
            self._path_label.setText(path.name)
            self._path_label.setToolTip(str(path))

    # ==================================================================
    # Theme toggle / Script Editor launcher
    # ==================================================================

    def _toggle_theme(self) -> None:
        app = QApplication.instance()
        if app is None:
            return
        new_mode = "dark" if resolved_mode() == "light" else "light"
        apply_theme(app, mode=new_mode)
        ui_settings.set_value("theme", new_mode)
        self._btn_theme.setIcon(
            icon("theme_dark" if resolved_mode() == "light" else "theme_light")
        )

    def _launch_script_editor(self) -> None:
        if self._current_path is None:
            QMessageBox.information(
                self,
                "Script Editor",
                "Open or save a YAML config first — scripts are stored alongside it.",
            )
            return
        try:
            from ..script_editor.window import ScriptEditorWindow
        except Exception as err:  # noqa: BLE001
            QMessageBox.information(
                self,
                "Script Editor",
                f"Script Editor is still under development (Phase 4).\n\n{err}",
            )
            return
        editor = ScriptEditorWindow(self._current_path, parent=self)
        editor.show()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setDesktopFileName("pytrack-config")
    app.setWindowIcon(app_icon())
    mode = ui_settings.get("theme", "auto")
    apply_theme(app, mode=mode)

    initial = sys.argv[1] if len(sys.argv) > 1 else None
    win = ConfigEditorWindow(initial_path=initial)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
