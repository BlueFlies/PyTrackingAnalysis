"""
PyQt6 UI for editing tracking_config.yaml and running analyses.

Usage:
    python analysis_ui.py
    python analysis_ui.py /path/to/project
"""

from __future__ import annotations

import argparse
import io
import os
import sys
import traceback
from contextlib import redirect_stderr, redirect_stdout

import yaml

# Experiment imports matplotlib.pyplot at module import time. Select a non-GUI
# backend before that import so analysis runs do not touch Qt's GUI backend
# from worker threads (and so use("Agg") is not ignored as "too late").
import matplotlib

matplotlib.use("Agg")

from PyQt6.QtCore import QThread, Qt, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QPixmap, QTextCursor
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

# Import the structured config-editor widgets from config_ui so they are not
# duplicated here.  config_ui.main() is protected by __name__ == "__main__",
# so importing is safe.
from config_ui import CountingRegionsTab, GlobalTab, TrackingRegionsTab

from Experiment import Experiment, batch_analyze


# ---------------------------------------------------------------------------
# Live-log IO helper
# ---------------------------------------------------------------------------

class _SignalIO(io.TextIOBase):
    """Writable text stream that fires a Qt signal on every write().

    When used with redirect_stdout / redirect_stderr inside a QThread, Qt
    automatically queues the signal across the thread boundary, so the
    connected slot runs safely on the GUI thread.
    """

    def __init__(self, signal: pyqtSignal) -> None:
        super().__init__()
        self._signal = signal

    def write(self, text: str) -> int:
        if text:
            self._signal.emit(text)
        return len(text)

    def flush(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Background worker
# ---------------------------------------------------------------------------

class AnalysisWorker(QThread):
    finished_ok = pyqtSignal(str)
    failed = pyqtSignal(str)
    log_text = pyqtSignal(str)

    def __init__(self, mode: str, target_path: str) -> None:
        super().__init__()
        self.mode = mode
        self.target_path = target_path

    def run(self) -> None:
        sio = _SignalIO(self.log_text)
        try:
            with redirect_stdout(sio), redirect_stderr(sio):
                if self.mode == "single":
                    exp = Experiment(self.target_path)
                    exp.run_analysis()
                    exp.create_report()
                    message = f"Single analysis complete: {self.target_path}"
                else:
                    result = batch_analyze(self.target_path)
                    ok_count = sum(1 for s in result.values() if s == "ok")
                    lines = [f"Batch complete: {ok_count}/{len(result)} succeeded."]
                    for path, status in result.items():
                        tag = "OK  " if status == "ok" else "FAIL"
                        lines.append(f"  {tag}  {path}")
                        if status != "ok":
                            lines.append(f"       {status}")
                    message = "\n".join(lines)
            self.finished_ok.emit(message)
        except Exception:
            self.log_text.emit(traceback.format_exc())
            self.failed.emit("Analysis failed — see log above for details.")


# ---------------------------------------------------------------------------
# Config tab  (Form sub-tab + YAML sub-tab)
# ---------------------------------------------------------------------------

class ConfigTab(QWidget):
    """Config tab with two editing modes:

    * **Form** – structured drop-downs / tables (GlobalTab, TrackingRegionsTab,
      CountingRegionsTab imported from config_ui).  Easy for routine edits.
    * **YAML** – raw plain-text editor.  Preserves comments; suited for
      power-user edits and for inspecting exactly what will be written.

    The two views are kept independent.  Explicit "Load from …" buttons let
    the user sync in either direction on demand.  The **Save** button always
    writes from whichever sub-tab is currently active; when the Form is
    active it first dumps the form to YAML (comment-free) and saves that.
    """

    def __init__(self) -> None:
        super().__init__()
        self._config_path: str = ""
        self._disk_text: str = ""   # text as last written to / read from disk

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self.sub_tabs = QTabWidget()

        # ── Form sub-tab ───────────────────────────────────────────────────
        form_container = QWidget()
        fc_layout = QVBoxLayout(form_container)
        fc_layout.setContentsMargins(0, 4, 0, 0)

        sync_btn = QPushButton("⟵  Load values from YAML into Form")
        sync_btn.setToolTip("Parse the current YAML editor text and populate the form fields.")
        sync_btn.clicked.connect(self._yaml_to_form)
        fc_layout.addWidget(sync_btn)

        self.global_tab = GlobalTab()
        self.tracking_tab = TrackingRegionsTab(self.global_tab)
        self.counting_tab = CountingRegionsTab()
        form_inner = QTabWidget()
        form_inner.addTab(self.global_tab, "Global")
        form_inner.addTab(self.tracking_tab, "Tracking regions")
        form_inner.addTab(self.counting_tab, "Counting regions")
        fc_layout.addWidget(form_inner, 1)

        # ── YAML sub-tab ───────────────────────────────────────────────────
        yaml_container = QWidget()
        yc_layout = QVBoxLayout(yaml_container)
        yc_layout.setContentsMargins(0, 4, 0, 0)

        dump_btn = QPushButton("⟵  Load values from Form into YAML")
        dump_btn.setToolTip(
            "Dump the form into the YAML editor.  "
            "Note: existing YAML comments will be removed."
        )
        dump_btn.clicked.connect(self._form_to_yaml_explicit)
        yc_layout.addWidget(dump_btn)

        self.yaml_editor = QPlainTextEdit()
        self.yaml_editor.setPlaceholderText("# tracking_config.yaml will appear here")
        mono = self.yaml_editor.font()
        mono.setFamily("Monospace")
        self.yaml_editor.setFont(mono)
        yc_layout.addWidget(self.yaml_editor, 1)

        self.sub_tabs.addTab(form_container, "Form")
        self.sub_tabs.addTab(yaml_container, "YAML")
        layout.addWidget(self.sub_tabs, 1)

        # ── shared action buttons ──────────────────────────────────────────
        btn_row = QHBoxLayout()
        save_btn = QPushButton("Save config")
        save_btn.clicked.connect(self.save)
        validate_btn = QPushButton("Validate YAML")
        validate_btn.clicked.connect(self._validate_yaml)
        reload_btn = QPushButton("Reload from file")
        reload_btn.clicked.connect(self.load_from_disk)
        btn_row.addWidget(save_btn)
        btn_row.addWidget(validate_btn)
        btn_row.addWidget(reload_btn)
        btn_row.addStretch()
        note = QLabel("Saving via the Form view removes YAML comments.")
        note.setStyleSheet("color: gray; font-style: italic;")
        btn_row.addWidget(note)
        layout.addLayout(btn_row)

    # ── path / disk I/O ───────────────────────────────────────────────────

    def set_config_path(self, path: str) -> None:
        self._config_path = path

    def load_from_disk(self) -> None:
        if not self._config_path:
            return
        if not os.path.exists(self._config_path):
            self.yaml_editor.setPlainText("")
            self._disk_text = ""
            empty: dict = {}
            self.global_tab.load(empty)
            self.tracking_tab.load(empty)
            self.counting_tab.load(empty)
            return
        try:
            with open(self._config_path, "r", encoding="utf-8") as fh:
                text = fh.read()
        except Exception as exc:
            QMessageBox.critical(self, "Load failed", str(exc))
            return
        self._disk_text = text
        self.yaml_editor.setPlainText(text)
        # Populate the form silently — ignore parse errors so the user can
        # investigate in the YAML tab.
        try:
            config = yaml.safe_load(text) or {}
            self.global_tab.load(config)
            self.tracking_tab.load(config)
            self.counting_tab.load(config)
        except Exception:
            pass

    def has_unsaved_changes(self) -> bool:
        """True if the current editor state differs from what is on disk."""
        return self._current_yaml_text() != self._disk_text

    def save(self) -> bool:
        """Validate and save config to disk.  Returns True on success."""
        if not self._config_path:
            QMessageBox.warning(self, "No path", "No project directory is selected.")
            return False
        text = self._current_yaml_text()
        try:
            yaml.safe_load(text)
        except Exception as exc:
            QMessageBox.warning(self, "Invalid YAML", str(exc))
            return False
        try:
            with open(self._config_path, "w", encoding="utf-8") as fh:
                fh.write(text)
            self._disk_text = text
            return True
        except Exception as exc:
            QMessageBox.critical(self, "Save failed", str(exc))
            return False

    # ── internal helpers ──────────────────────────────────────────────────

    def _current_yaml_text(self) -> str:
        """YAML text for the currently active sub-tab."""
        if self.sub_tabs.currentIndex() == 0:   # Form is active
            try:
                cfg = self._dump_form()
                return yaml.dump(
                    cfg, default_flow_style=False, allow_unicode=True, sort_keys=False
                )
            except Exception:
                return self.yaml_editor.toPlainText()
        return self.yaml_editor.toPlainText()

    def _dump_form(self) -> dict:
        cfg: dict = {}
        cfg.update(self.global_tab.dump())
        cfg.update(self.tracking_tab.dump())
        cfg.update(self.counting_tab.dump())
        return cfg

    def _validate_yaml(self) -> None:
        text = self._current_yaml_text()
        try:
            yaml.safe_load(text)
            QMessageBox.information(self, "Valid", "YAML is valid.")
        except Exception as exc:
            QMessageBox.warning(self, "Invalid YAML", str(exc))

    def _yaml_to_form(self) -> None:
        """Parse YAML editor text → populate form fields."""
        text = self.yaml_editor.toPlainText()
        try:
            config = yaml.safe_load(text) or {}
            self.global_tab.load(config)
            self.tracking_tab.load(config)
            self.counting_tab.load(config)
        except Exception as exc:
            QMessageBox.warning(self, "Invalid YAML", f"Cannot populate form:\n{exc}")

    def _form_to_yaml_explicit(self) -> None:
        """Dump form → YAML editor (user-initiated; they accept comment loss)."""
        try:
            cfg = self._dump_form()
            text = yaml.dump(
                cfg, default_flow_style=False, allow_unicode=True, sort_keys=False
            )
            self.yaml_editor.setPlainText(text)
        except Exception as exc:
            QMessageBox.warning(self, "Form error", str(exc))


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------

class TrackingAnalysisUI(QMainWindow):
    def __init__(self, initial_project_dir: str | None = None) -> None:
        super().__init__()
        self.setWindowTitle("PyTracking Analysis UI")
        self.resize(1150, 840)
        self._worker: AnalysisWorker | None = None

        self.project_dir = (
            os.path.abspath(initial_project_dir) if initial_project_dir else os.getcwd()
        )
        self.config_path: str = ""

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QVBoxLayout(central)
        main_layout.addWidget(self._build_project_group())

        self.tabs = QTabWidget()
        self.config_tab_widget = ConfigTab()
        self.tabs.addTab(self.config_tab_widget, "Config")
        self.tabs.addTab(self._build_run_tab(), "Run")
        self.tabs.addTab(self._build_outputs_tab(), "Outputs")
        main_layout.addWidget(self.tabs)

        self._sync_project_dir(self.project_dir, load_config=True)

    # ── UI builders ───────────────────────────────────────────────────────

    def _build_project_group(self) -> QGroupBox:
        group = QGroupBox("Project directory")
        layout = QHBoxLayout(group)

        self.project_dir_edit = QLineEdit()
        self.project_dir_edit.setPlaceholderText(
            "Select the project directory that contains tracking_config.yaml and data/"
        )
        self.project_dir_edit.editingFinished.connect(self._on_project_edit_finished)

        choose_btn = QPushButton("Choose…")
        choose_btn.clicked.connect(self._choose_project_dir)
        reload_btn = QPushButton("Reload")
        reload_btn.clicked.connect(self._reload_all)

        layout.addWidget(self.project_dir_edit, 1)
        layout.addWidget(choose_btn)
        layout.addWidget(reload_btn)
        return group

    def _build_run_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        path_group = QGroupBox("Analysis paths")
        form = QFormLayout(path_group)

        # Single-project path — independently editable from the project dir.
        single_row = QHBoxLayout()
        self.single_dir_edit = QLineEdit()
        self.single_dir_edit.setPlaceholderText(
            "Directory containing tracking_config.yaml and data/"
        )
        single_browse = QPushButton("Browse…")
        single_browse.clicked.connect(self._browse_single_dir)
        single_row.addWidget(self.single_dir_edit, 1)
        single_row.addWidget(single_browse)
        form.addRow("Single project:", single_row)

        # Batch-parent path — one level above the individual experiment dirs.
        batch_row = QHBoxLayout()
        self.batch_parent_edit = QLineEdit()
        self.batch_parent_edit.setPlaceholderText(
            "Parent directory containing multiple experiment sub-directories"
        )
        batch_browse = QPushButton("Browse…")
        batch_browse.clicked.connect(self._browse_batch_dir)
        batch_row.addWidget(self.batch_parent_edit, 1)
        batch_row.addWidget(batch_browse)
        form.addRow("Batch parent:", batch_row)

        layout.addWidget(path_group)

        run_row = QHBoxLayout()
        self.run_single_btn = QPushButton("Run Single Analysis")
        self.run_single_btn.clicked.connect(self._run_single_analysis)
        self.run_batch_btn = QPushButton("Run Batch Analysis")
        self.run_batch_btn.clicked.connect(self._run_batch_analysis)
        run_row.addWidget(self.run_single_btn)
        run_row.addWidget(self.run_batch_btn)
        run_row.addStretch()
        layout.addLayout(run_row)

        # Indeterminate progress bar — visible only while a worker is running.
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        layout.addWidget(QLabel("Execution log"))
        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        layout.addWidget(self.log_view, 1)
        return tab

    def _build_outputs_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        # ── left pane: file list ───────────────────────────────────────────
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("Output files (analysis/ and qc/)"))

        self.output_list = QListWidget()
        self.output_list.itemSelectionChanged.connect(self._preview_selected_output)
        left_layout.addWidget(self.output_list, 1)

        left_btns = QHBoxLayout()
        refresh_btn = QPushButton("Refresh")
        refresh_btn.clicked.connect(self._refresh_output_files)
        open_btn = QPushButton("Open externally")
        open_btn.clicked.connect(self._open_selected_output)
        left_btns.addWidget(refresh_btn)
        left_btns.addWidget(open_btn)
        left_btns.addStretch()
        left_layout.addLayout(left_btns)

        # ── right pane: preview (stacked) ─────────────────────────────────
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(QLabel("Preview"))

        self.preview_stack = QStackedWidget()

        # 0 – text
        self.text_preview = QPlainTextEdit()
        self.text_preview.setReadOnly(True)
        self.preview_stack.addWidget(self.text_preview)

        # 1 – image (inside a scroll area so large plots can be panned)
        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        img_scroll = QScrollArea()
        img_scroll.setWidget(self.image_label)
        img_scroll.setWidgetResizable(True)
        self.preview_stack.addWidget(img_scroll)

        # 2 – no-preview placeholder
        no_preview = QLabel(
            "Preview not available for this file type.\nUse 'Open externally'."
        )
        no_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_stack.addWidget(no_preview)

        right_layout.addWidget(self.preview_stack, 1)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([350, 750])
        layout.addWidget(splitter, 1)
        return tab

    # ── project directory plumbing ────────────────────────────────────────

    def _on_project_edit_finished(self) -> None:
        path = self.project_dir_edit.text().strip()
        if path:
            self._sync_project_dir(path, load_config=True)

    def _choose_project_dir(self) -> None:
        chosen = QFileDialog.getExistingDirectory(
            self, "Choose project directory", self.project_dir
        )
        if chosen:
            self._sync_project_dir(chosen, load_config=True)

    def _sync_project_dir(self, path: str, *, load_config: bool) -> None:
        absolute = os.path.abspath(path)
        self.project_dir = absolute
        self.config_path = os.path.join(self.project_dir, "tracking_config.yaml")
        self.project_dir_edit.setText(self.project_dir)
        # Seed the run-tab path fields; the user can override them independently.
        self.single_dir_edit.setText(self.project_dir)
        self.batch_parent_edit.setText(self.project_dir)
        self.config_tab_widget.set_config_path(self.config_path)
        if load_config:
            self.config_tab_widget.load_from_disk()
        self._refresh_output_files()

    def _reload_all(self) -> None:
        self.config_tab_widget.load_from_disk()
        self._refresh_output_files()

    # ── run-tab helpers ───────────────────────────────────────────────────

    def _browse_single_dir(self) -> None:
        start = self.single_dir_edit.text() or self.project_dir
        chosen = QFileDialog.getExistingDirectory(
            self, "Choose single project directory", start
        )
        if chosen:
            self.single_dir_edit.setText(chosen)

    def _browse_batch_dir(self) -> None:
        start = self.batch_parent_edit.text() or self.project_dir
        chosen = QFileDialog.getExistingDirectory(
            self, "Choose batch parent directory", start
        )
        if chosen:
            self.batch_parent_edit.setText(chosen)

    def _run_single_analysis(self) -> None:
        path = self.single_dir_edit.text().strip()
        if not os.path.isdir(path):
            QMessageBox.warning(self, "Invalid path", "Single project directory is not valid.")
            return
        cfg = os.path.join(path, "tracking_config.yaml")
        if not os.path.isfile(cfg):
            QMessageBox.warning(self, "Missing config", f"Could not find:\n{cfg}")
            return
        if self._prompt_save_if_dirty():
            return
        self._start_worker("single", path)

    def _run_batch_analysis(self) -> None:
        path = self.batch_parent_edit.text().strip()
        if not os.path.isdir(path):
            QMessageBox.warning(self, "Invalid path", "Batch parent directory is not valid.")
            return
        if self._prompt_save_if_dirty():
            return
        self._start_worker("batch", path)

    def _prompt_save_if_dirty(self) -> bool:
        """Offer to save unsaved config changes before running.

        Returns True if the caller should abort (user cancelled or save failed).
        """
        if not self.config_tab_widget.has_unsaved_changes():
            return False
        reply = QMessageBox.question(
            self,
            "Unsaved config changes",
            "The config has unsaved changes. Save before running?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Cancel:
            return True
        if reply == QMessageBox.StandardButton.Save:
            return not self.config_tab_widget.save()  # abort if save failed
        return False  # Discard → proceed without saving

    def _start_worker(self, mode: str, path: str) -> None:
        if self._worker is not None and self._worker.isRunning():
            QMessageBox.information(self, "Busy", "Another analysis is already running.")
            return

        self.run_single_btn.setEnabled(False)
        self.run_batch_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self._append_log(f"Starting {mode} analysis for: {path}\n")

        worker = AnalysisWorker(mode, path)
        self._worker = worker
        worker.log_text.connect(self._append_log)
        worker.finished_ok.connect(self._on_worker_success)
        worker.failed.connect(self._on_worker_failure)
        # Ensure the C++ object is cleaned up once the thread finishes.
        worker.finished.connect(worker.deleteLater)
        worker.start()

    def _on_worker_success(self, message: str) -> None:
        self.run_single_btn.setEnabled(True)
        self.run_batch_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self._append_log(f"\n{message}\n")
        self._refresh_output_files()

    def _on_worker_failure(self, err: str) -> None:
        self.run_single_btn.setEnabled(True)
        self.run_batch_btn.setEnabled(True)
        self.progress_bar.setVisible(False)
        self._append_log(f"\n{err}\n")
        QMessageBox.critical(self, "Analysis failed", err)

    def _append_log(self, text: str) -> None:
        """Append text to the log view, streaming it to the end."""
        if not text:
            return
        # Bug fix: the original code called
        #   self.log_view.moveCursor(self.log_view.textCursor().MoveOperation.End)
        # which accesses MoveOperation on a QTextCursor *instance*, not the
        # class.  The correct form is QTextCursor.MoveOperation.End.
        self.log_view.moveCursor(QTextCursor.MoveOperation.End)
        self.log_view.insertPlainText(text)
        self.log_view.moveCursor(QTextCursor.MoveOperation.End)

    # ── outputs tab ───────────────────────────────────────────────────────

    def _refresh_output_files(self) -> None:
        """Populate the file list.

        Scans project_dir itself AND every immediate sub-directory so that
        batch-mode results (stored in experiment_subdir/analysis/ etc.) are
        visible alongside single-run results.
        """
        self.output_list.clear()
        roots = [self.project_dir]
        try:
            with os.scandir(self.project_dir) as it:
                roots.extend(e.path for e in it if e.is_dir())
        except OSError:
            pass

        seen: set[str] = set()
        for root in roots:
            for sub in ("analysis", "qc"):
                folder = os.path.join(root, sub)
                if not os.path.isdir(folder) or folder in seen:
                    continue
                seen.add(folder)
                rel_root = os.path.relpath(root, self.project_dir)
                try:
                    names = sorted(os.listdir(folder))
                except OSError:
                    continue
                for name in names:
                    full = os.path.join(folder, name)
                    if not os.path.isfile(full):
                        continue
                    label = (
                        f"{sub}/{name}"
                        if rel_root == "."
                        else f"{rel_root}/{sub}/{name}"
                    )
                    item = QListWidgetItem(label)
                    item.setData(Qt.ItemDataRole.UserRole, full)
                    self.output_list.addItem(item)

    def _preview_selected_output(self) -> None:
        item = self.output_list.currentItem()
        if item is None:
            self.preview_stack.setCurrentIndex(2)
            return
        path = item.data(Qt.ItemDataRole.UserRole)
        if not path:
            self.preview_stack.setCurrentIndex(2)
            return

        lower = path.lower()
        if lower.endswith((".txt", ".csv", ".yaml", ".yml", ".log")):
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as fh:
                    self.text_preview.setPlainText(fh.read())
            except Exception as exc:
                self.text_preview.setPlainText(f"Could not read file:\n{exc}")
            self.preview_stack.setCurrentIndex(0)
        elif lower.endswith((".png", ".jpg", ".jpeg", ".bmp", ".gif")):
            pixmap = QPixmap(path)
            if pixmap.isNull():
                self.preview_stack.setCurrentIndex(2)
            else:
                self.image_label.setPixmap(pixmap)
                self.image_label.resize(pixmap.size())
                self.preview_stack.setCurrentIndex(1)
        else:
            self.preview_stack.setCurrentIndex(2)

    def _open_selected_output(self) -> None:
        item = self.output_list.currentItem()
        if item is None:
            return
        path = item.data(Qt.ItemDataRole.UserRole)
        if path and os.path.exists(path):
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="PyTracking analysis desktop UI")
    parser.add_argument(
        "project_dir",
        nargs="?",
        default=None,
        help="Project directory containing tracking_config.yaml and data/",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    app = QApplication(sys.argv)
    window = TrackingAnalysisUI(initial_project_dir=args.project_dir)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
