"""Note editing dialog."""

from __future__ import annotations

from ukm.qt import (
    QDialog, QDialogButtonBox, QVBoxLayout, QLabel, QTextEdit, Qt,
)
from ukm.core.kernel import KernelEntry


class NoteDialog(QDialog):

    def __init__(self, entry: KernelEntry, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Note — {entry.display_name}")
        self.setMinimumWidth(400)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(f"Note for <b>{entry.display_name}</b>:"))

        self._edit = QTextEdit()
        self._edit.setPlainText(entry.notes)
        self._edit.setMinimumHeight(100)
        layout.addWidget(self._edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def note_text(self) -> str:
        return self._edit.toPlainText().strip()
