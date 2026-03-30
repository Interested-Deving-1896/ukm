"""
Qt table model for a list of KernelEntry objects.

Used by both the unified list view and each per-family tab.
Supports sorting and filtering via QSortFilterProxyModel.
"""

from __future__ import annotations

from ukm.qt import (
    Qt, QAbstractTableModel, QModelIndex, QPersistentModelIndex,
    QColor, QFont,
)
from ukm.core.kernel import KernelEntry, KernelStatus

# Column indices
COL_VERSION  = 0
COL_FLAVOR   = 1
COL_FAMILY   = 2
COL_ARCH     = 3
COL_STATUS   = 4
COL_HELD     = 5
COL_PROVIDER = 6
COL_NOTES    = 7

HEADERS = ["Version", "Flavor", "Family", "Arch", "Status", "Held", "Provider", "Notes"]

# Status colours
_STATUS_COLOURS = {
    KernelStatus.RUNNING:   QColor("#2ecc71"),   # green
    KernelStatus.INSTALLED: QColor("#3498db"),   # blue
    KernelStatus.HELD:      QColor("#e67e22"),   # orange
    KernelStatus.AVAILABLE: None,
}


class KernelTableModel(QAbstractTableModel):

    def __init__(self, entries: list[KernelEntry] | None = None, parent=None) -> None:
        super().__init__(parent)
        self._entries: list[KernelEntry] = entries or []

    # ------------------------------------------------------------------
    # QAbstractTableModel interface
    # ------------------------------------------------------------------

    def rowCount(self, parent=QModelIndex()) -> int:
        return len(self._entries)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(HEADERS)

    def headerData(self, section: int, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return HEADERS[section]
        return None

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self._entries):
            return None

        entry = self._entries[index.row()]
        col = index.column()

        if role == Qt.ItemDataRole.DisplayRole:
            return self._display(entry, col)

        if role == Qt.ItemDataRole.ForegroundRole:
            colour = _STATUS_COLOURS.get(entry.status)
            if colour:
                return colour

        if role == Qt.ItemDataRole.FontRole:
            if entry.is_running:
                f = QFont()
                f.setBold(True)
                return f

        if role == Qt.ItemDataRole.UserRole:
            # Return the raw KernelEntry for the delegate / action layer
            return entry

        if role == Qt.ItemDataRole.ToolTipRole:
            return self._tooltip(entry)

        return None

    # ------------------------------------------------------------------
    # Data update
    # ------------------------------------------------------------------

    def set_entries(self, entries: list[KernelEntry]) -> None:
        self.beginResetModel()
        self._entries = entries
        self.endResetModel()

    def entry_at(self, row: int) -> KernelEntry | None:
        if 0 <= row < len(self._entries):
            return self._entries[row]
        return None

    def update_entry(self, entry: KernelEntry) -> None:
        for i, e in enumerate(self._entries):
            if (e.version == entry.version and
                    e.provider_id == entry.provider_id and
                    e.flavor == entry.flavor):
                self._entries[i] = entry
                top_left = self.index(i, 0)
                bottom_right = self.index(i, len(HEADERS) - 1)
                self.dataChanged.emit(top_left, bottom_right)
                return

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _display(entry: KernelEntry, col: int) -> str:
        if col == 0: return str(entry.version)
        if col == 1: return entry.flavor
        if col == 2: return entry.family.value
        if col == 3: return entry.arch
        if col == 4: return entry.status.name.lower()
        if col == 5: return "●" if entry.held else ""
        if col == 6: return entry.provider_id
        if col == 7: return entry.notes[:60] + "…" if len(entry.notes) > 60 else entry.notes
        return ""

    @staticmethod
    def _tooltip(entry: KernelEntry) -> str:
        lines = [
            f"Version:  {entry.version}",
            f"Family:   {entry.family.value}",
            f"Provider: {entry.provider_id}",
            f"Arch:     {entry.arch}",
            f"Flavor:   {entry.flavor}",
            f"Status:   {entry.status.name}",
        ]
        if entry.description:
            lines.append(f"Desc:     {entry.description}")
        if entry.notes:
            lines.append(f"Notes:    {entry.notes}")
        if entry.source_url:
            lines.append(f"URL:      {entry.source_url}")
        return "\n".join(lines)
