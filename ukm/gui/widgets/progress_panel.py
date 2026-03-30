"""
Progress panel widget — phase label + progress bar for install/remove operations.

Displayed between the toolbar and the kernel table during long-running operations.
Hidden when idle.

Phase detection is based on keywords in the log stream:
  "Downloading"  → Downloading packages
  "Verifying"    → Verifying checksums
  "Installing"   → Installing packages
  "Removing"     → Removing packages
  "Rebuilding"   → Rebuilding DKMS modules
  "✓" / "Done"   → Complete
"""

from __future__ import annotations

from ukm.qt import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

# Ordered list of (keyword, phase label) pairs.
# First match wins.
_PHASE_PATTERNS: list[tuple[str, str]] = [
    ("Downloading", "Downloading packages…"),
    ("Verifying", "Verifying checksums…"),
    ("Unpacking", "Unpacking…"),
    ("Setting up", "Configuring…"),
    ("Installing", "Installing…"),
    ("Removing", "Removing…"),
    ("Purging", "Purging…"),
    ("Rebuilding DKMS", "Rebuilding DKMS modules…"),
    ("autoinstall", "Rebuilding DKMS modules…"),
    ("Building", "Building…"),
    ("Compiling", "Compiling…"),
    ("genkernel", "Running genkernel…"),
    ("make", "Compiling kernel…"),
    ("✓", "Complete"),
    ("Done", "Complete"),
    ("Error", "Error"),
    ("FAILED", "Error"),
]


class ProgressPanel(QWidget):
    """
    A slim panel showing the current operation phase and an indeterminate
    progress bar. Call start() when an operation begins and stop() when done.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._setup_ui()
        self.hide()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(2)

        row = QHBoxLayout()

        self._phase_label = QLabel("Working…")
        self._phase_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred
        )
        row.addWidget(self._phase_label)

        self._bar = QProgressBar()
        self._bar.setRange(0, 0)  # indeterminate
        self._bar.setFixedHeight(14)
        self._bar.setFixedWidth(200)
        self._bar.setTextVisible(False)
        row.addWidget(self._bar)

        layout.addLayout(row)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self, message: str = "Working…") -> None:
        """Show the panel and begin the indeterminate animation."""
        self._phase_label.setText(message)
        self._bar.setRange(0, 0)
        self.show()

    def stop(self, success: bool = True) -> None:
        """Stop the animation and hide the panel after a brief moment."""
        if success:
            self._phase_label.setText("Complete")
        else:
            self._phase_label.setText("Failed — see log for details")
        self._bar.setRange(0, 1)
        self._bar.setValue(1 if success else 0)
        # Hide after a short delay so the user sees the final state
        from ukm.qt import QTimer
        QTimer.singleShot(1500, self.hide)

    def update_phase(self, log_line: str) -> None:
        """
        Inspect a log line and update the phase label if a known keyword
        is found. Called for each line emitted by the operation worker.
        """
        for keyword, label in _PHASE_PATTERNS:
            if keyword.lower() in log_line.lower():
                self._phase_label.setText(label)
                break

    def set_phase(self, label: str) -> None:
        """Directly set the phase label text."""
        self._phase_label.setText(label)
