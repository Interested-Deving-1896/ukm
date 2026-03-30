"""
Log panel widget — live streaming output for install/remove/compile operations.

Displayed at the bottom of the main window, collapsible.
"""

from __future__ import annotations

from ukm.qt import (
    QFont,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class LogPanel(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # Header bar
        header = QHBoxLayout()
        self._label = QLabel("Details")
        self._label.setStyleSheet("font-weight: bold; padding: 2px 4px;")
        self._toggle_btn = QPushButton("Hide")
        self._toggle_btn.setFixedWidth(60)
        self._toggle_btn.setFlat(True)
        self._toggle_btn.clicked.connect(self._toggle)
        self._clear_btn = QPushButton("Clear")
        self._clear_btn.setFixedWidth(60)
        self._clear_btn.setFlat(True)
        self._clear_btn.clicked.connect(self.clear)
        header.addWidget(self._label)
        header.addStretch()
        header.addWidget(self._clear_btn)
        header.addWidget(self._toggle_btn)
        layout.addLayout(header)

        # Text area
        self._text = QTextEdit()
        self._text.setReadOnly(True)
        self._text.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        font = QFont("Monospace")
        font.setStyleHint(QFont.StyleHint.TypeWriter)
        font.setPointSize(9)
        self._text.setFont(font)
        self._text.setMinimumHeight(120)
        self._text.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self._text)

        self._visible = True

    def append(self, text: str) -> None:
        """Append text (may contain newlines) to the log."""
        cursor = self._text.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertText(text)
        self._text.setTextCursor(cursor)
        self._text.ensureCursorVisible()

    def clear(self) -> None:
        self._text.clear()

    def show_panel(self) -> None:
        self._text.setVisible(True)
        self._toggle_btn.setText("Hide")
        self._visible = True

    def hide_panel(self) -> None:
        self._text.setVisible(False)
        self._toggle_btn.setText("Show")
        self._visible = False

    def _toggle(self) -> None:
        if self._visible:
            self.hide_panel()
        else:
            self.show_panel()
