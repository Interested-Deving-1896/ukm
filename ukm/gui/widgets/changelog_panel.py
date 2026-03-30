"""
Changelog / release notes panel.

Shown in a side panel or dialog when the user selects a kernel entry.
Fetches changelog text in a background thread so the UI never blocks.
"""

from __future__ import annotations

from ukm.core.kernel import KernelEntry
from ukm.qt import (
    QFont, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
    QTextEdit, QThread, QVBoxLayout, QWidget, Signal, Slot,
)


class _FetchWorker(QThread):
    done  = Signal(str)
    error = Signal(str)

    def __init__(self, entry: KernelEntry) -> None:
        super().__init__()
        self._entry = entry

    def run(self) -> None:
        from ukm.core.changelog import fetch
        try:
            text = fetch(
                self._entry.provider_id,
                str(self._entry.version),
                self._entry.flavor,
            )
            self.done.emit(text or "(No changelog available for this kernel.)")
        except Exception as e:
            self.error.emit(str(e))


class ChangelogPanel(QWidget):
    """
    A collapsible panel that shows the changelog for the selected kernel.
    Embed it in the main window's right-hand splitter or as a dockable widget.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._worker: _FetchWorker | None = None
        self._current_entry: KernelEntry | None = None
        self._setup_ui()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def show_entry(self, entry: KernelEntry) -> None:
        """Load and display the changelog for the given kernel entry."""
        if self._current_entry and (
            self._current_entry.version == entry.version
            and self._current_entry.provider_id == entry.provider_id
        ):
            return  # already showing this entry

        self._current_entry = entry
        self._title.setText(
            f"<b>Release notes</b> — {entry.display_name} "
            f"<span style='color:#a6adc8'>({entry.provider_id})</span>"
        )
        self._text.setPlainText("Loading…")
        self._refresh_btn.setEnabled(False)

        if self._worker and self._worker.isRunning():
            self._worker.terminate()

        self._worker = _FetchWorker(entry)
        self._worker.done.connect(self._on_done)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def clear(self) -> None:
        self._current_entry = None
        self._title.setText("<b>Release notes</b>")
        self._text.clear()

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Header
        header = QHBoxLayout()
        self._title = QLabel("<b>Release notes</b>")
        self._title.setWordWrap(True)
        header.addWidget(self._title, stretch=1)

        self._refresh_btn = QPushButton("↺")
        self._refresh_btn.setFixedWidth(28)
        self._refresh_btn.setToolTip("Re-fetch changelog (clears cache)")
        self._refresh_btn.setFlat(True)
        self._refresh_btn.clicked.connect(self._on_refresh)
        header.addWidget(self._refresh_btn)
        layout.addLayout(header)

        # Text area
        self._text = QTextEdit()
        self._text.setReadOnly(True)
        self._text.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        font = QFont("Monospace")
        font.setStyleHint(QFont.StyleHint.TypeWriter)
        font.setPointSize(9)
        self._text.setFont(font)
        self._text.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self._text)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    @Slot(str)
    def _on_done(self, text: str) -> None:
        self._text.setPlainText(text)
        self._refresh_btn.setEnabled(True)

    @Slot(str)
    def _on_error(self, msg: str) -> None:
        self._text.setPlainText(f"Error fetching changelog:\n{msg}")
        self._refresh_btn.setEnabled(True)

    def _on_refresh(self) -> None:
        if self._current_entry:
            from ukm.core.changelog import clear_cache
            clear_cache(self._current_entry.provider_id)
            self.show_entry(self._current_entry)
            # Force re-fetch by clearing the current entry reference
            entry = self._current_entry
            self._current_entry = None
            self.show_entry(entry)
