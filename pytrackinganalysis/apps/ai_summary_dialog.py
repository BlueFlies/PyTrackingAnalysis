"""The AI Summary dialog — provider/model choice + generation (ADR-0004).

Opened from the Hub's AI card. The dialog only ever offers providers whose
API key is present; the actual call runs on the Hub's single task worker (so
it cannot race another analysis task), writes ``<name>_AI_Summary.txt``, and
automatically rebuilds the report PDF so a stale report never sits beside a
fresh summary.
"""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QToolButton,
    QVBoxLayout,
)

from ..ai import available_providers, model_catalog
from ..help import HelpButton
from ..ui import ActionButton, Category, icon
from ..ui import settings as ui_settings
from .common import TaskWorker, shutdown_worker


class AiSummaryDialog(QDialog):
    """Choose a provider/model, generate the AI Summary, review the result."""

    def __init__(self, hub) -> None:
        super().__init__(hub)
        self._hub = hub
        self._running = False
        self.setWindowTitle("AI summary")
        self.setMinimumWidth(560)

        lay = QVBoxLayout(self)

        header_row = QHBoxLayout()
        intro = QLabel(
            "Sends this experiment's report content — figures, statistics, "
            "and summary tables — to the chosen provider, which writes a "
            "one-page summary. The summary is saved to analysis/, embedded "
            "in the report (clearly labeled as AI-generated), and the report "
            "PDF is rebuilt automatically."
        )
        intro.setWordWrap(True)
        header_row.addWidget(intro, 1)
        header_row.addWidget(HelpButton("ai_summary", tooltip="AI summary"))
        lay.addLayout(header_row)

        form = QFormLayout()
        self._provider_combo = QComboBox(self)
        self._providers = available_providers()
        for provider in self._providers:
            self._provider_combo.addItem(provider.display_name,
                                         provider.provider_name)
        self._provider_combo.currentIndexChanged.connect(self._populate_models)
        self._model_combo = QComboBox(self)
        # Models come from a cached live fetch (model_catalog); this button
        # forces a refresh, and a stale cache refreshes itself on open.
        self._models_refresh_btn = QToolButton(self)
        self._models_refresh_btn.setIcon(icon("refresh", category=Category.AI))
        self._models_refresh_btn.setToolTip(
            "Fetch the providers' current model lists.")
        self._models_refresh_btn.clicked.connect(
            lambda: self._start_model_refresh(auto=False))
        model_row = QHBoxLayout()
        model_row.addWidget(self._model_combo, 1)
        model_row.addWidget(self._models_refresh_btn)
        form.addRow("Provider:", self._provider_combo)
        form.addRow("Model:", model_row)
        lay.addLayout(form)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        self._status.setStyleSheet("color: palette(mid); font-style: italic;")
        lay.addWidget(self._status)

        self._result = QPlainTextEdit(self)
        self._result.setReadOnly(True)
        self._result.setPlaceholderText("The generated summary appears here.")
        self._result.setMinimumHeight(220)
        lay.addWidget(self._result, 1)

        buttons = QHBoxLayout()
        self._generate_btn = ActionButton(
            "Generate AI summary", Category.AI, icon_name="ai", primary=True)
        self._generate_btn.clicked.connect(self._on_generate)
        self._close_btn = QPushButton("Close", self)
        self._close_btn.clicked.connect(self.reject)
        buttons.addWidget(self._generate_btn, 1)
        buttons.addWidget(self._close_btn)
        lay.addLayout(buttons)

        self._refresh_worker: TaskWorker | None = None
        self._restore_last_choice()
        self._populate_models()
        self._show_existing_summary()
        if any(model_catalog.needs_refresh(p) for p in self._providers):
            self._start_model_refresh(auto=True)

    # ---------------- choices ----------------

    def _restore_last_choice(self) -> None:
        last = ui_settings.get("ai_provider")
        if last is not None:
            index = self._provider_combo.findData(last)
            if index >= 0:
                self._provider_combo.setCurrentIndex(index)

    def _current_provider(self):
        name = self._provider_combo.currentData()
        for provider in self._providers:
            if provider.provider_name == name:
                return provider
        return None

    def _populate_models(self) -> None:
        """Fill the model dropdown for the current provider from the cached
        live list (curated fallback when nothing was ever fetched)."""
        self._model_combo.clear()
        provider = self._current_provider()
        if provider is None:
            return
        models = model_catalog.cached_models(provider)
        for model in models:
            self._model_combo.addItem(model)
        last = ui_settings.get("ai_model")
        if last in models:
            self._model_combo.setCurrentText(last)

    # ---------------- model-list refresh ----------------

    def _start_model_refresh(self, auto: bool) -> None:
        """Fetch fresh model lists for every available provider.

        Runs on its own worker (network-only — it touches no experiment
        state, so it must not tie up the Hub's single analysis worker)."""
        if self._refresh_worker is not None and self._refresh_worker.isRunning():
            return
        providers = list(self._providers)
        if not providers:
            return
        self._refresh_auto = auto
        failures: list[str] = []

        def _do() -> str:
            for provider in providers:
                try:
                    model_catalog.refresh(provider)
                except Exception as err:  # noqa: BLE001 — collected, not fatal
                    failures.append(str(err))
            if len(failures) == len(providers):
                raise RuntimeError("; ".join(failures))
            return "ok"

        self._models_refresh_btn.setEnabled(False)
        if not auto:
            self._status.setText("Refreshing model lists…")
        worker = TaskWorker("Refresh AI models", _do)
        worker.finished_ok.connect(self._on_models_refreshed)
        worker.failed.connect(self._on_models_refresh_failed)
        self._refresh_worker = worker
        worker.start()

    def _on_models_refreshed(self, _msg: str) -> None:
        self._models_refresh_btn.setEnabled(True)
        current = self._model_combo.currentText()
        self._populate_models()
        if current and self._model_combo.findText(current) >= 0:
            self._model_combo.setCurrentText(current)
        if not self._refresh_auto:
            self._status.setText("Model lists updated.")

    def _on_models_refresh_failed(self, _msg: str) -> None:
        self._models_refresh_btn.setEnabled(True)
        # Degrade quietly: the cached/curated list already in the dropdown
        # keeps working (ADR-0004 — network problems never block).
        self._status.setText(
            "Could not refresh the model lists (offline?); using the saved "
            "lists.")

    def _show_existing_summary(self) -> None:
        exp = getattr(self._hub, "_exp", None)
        saved = exp.read_ai_summary() if exp is not None else None
        if saved:
            provenance, body = saved
            self._result.setPlainText(body)
            self._generate_btn.setText("Regenerate AI summary")
            self._status.setText(
                f"A saved summary exists ({provenance or 'unknown origin'}); "
                f"generating again replaces it.")

    # ---------------- generation ----------------

    def _on_generate(self) -> None:
        exp = getattr(self._hub, "_exp", None)
        if exp is None:
            QMessageBox.warning(self, "AI summary", "Load an experiment first.")
            return
        provider = self._current_provider()
        if provider is None:
            return
        provider_name = provider.provider_name
        model = self._model_combo.currentText()
        ui_settings.set_value("ai_provider", provider_name)
        ui_settings.set_value("ai_model", model)

        def _do() -> str:
            text = exp.generate_ai_summary(provider_name, model=model)
            # Rebuild immediately: a report on disk that lacks the summary it
            # sits next to is a trap (agreed flow, ADR-0004).
            exp.create_report()
            return text

        self._running = True
        self._generate_btn.setEnabled(False)
        self._close_btn.setEnabled(False)
        self._status.setText(f"Generating with {provider.display_name} "
                             f"({model})… this can take a minute.")
        # The Hub's single-worker guard applies, so this cannot run behind
        # another analysis task that is mutating the same experiment.
        self._hub._spawn_task_with_callbacks(
            "AI summary", _do, self._on_ok, self._on_fail)

    def _on_ok(self, text: str) -> None:
        self._finish()
        self._result.setPlainText(text)
        self._generate_btn.setText("Regenerate AI summary")
        self._status.setText("Summary saved and report rebuilt.")
        self._hub._log.append_line("AI summary complete; report rebuilt.")

    def _on_fail(self, msg: str) -> None:
        self._finish()
        self._status.setText("The AI summary failed; the report is unchanged.")
        self._hub._log_issue(msg)
        headline = msg.splitlines()[-1] if msg else "The AI summary failed."
        QMessageBox.warning(
            self, "AI summary",
            f"{headline}\n\nThe report was not changed. See the Errors tab "
            f"for details.")

    def _finish(self) -> None:
        self._running = False
        self._generate_btn.setEnabled(True)
        self._close_btn.setEnabled(True)

    # ---------------- teardown ----------------

    def reject(self) -> None:  # noqa: D102 — QDialog API
        if self._running:
            return  # the worker calls back into this dialog; stay open
        shutdown_worker(self._refresh_worker)
        super().reject()

    def closeEvent(self, event) -> None:  # noqa: N802 — Qt API
        if self._running:
            event.ignore()
            return
        shutdown_worker(self._refresh_worker)
        super().closeEvent(event)
