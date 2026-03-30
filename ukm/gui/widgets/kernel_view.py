"""
KernelView — a QTableView wired to a KernelTableModel with:
  - sortable columns
  - text filter bar
  - family/status filter dropdowns
  - right-click context menu
"""

from __future__ import annotations

from ukm.core.kernel import KernelEntry, KernelFamily, KernelStatus
from ukm.gui.kernel_model import KernelTableModel
from ukm.qt import (
    Qt,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTableView,
    QHeaderView,
    QLineEdit,
    QComboBox,
    QLabel,
    QSortFilterProxyModel,
    QAbstractItemView,
    QMenu,
    Signal,
)


class KernelFilterProxy(QSortFilterProxyModel):
    """Proxy that filters by text, family, and status."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._family_filter: str = ""
        self._status_filter: str = ""
        self.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setFilterKeyColumn(-1)  # search all columns

    def set_family(self, family: str) -> None:
        self._family_filter = family
        self.invalidateFilter()

    def set_status(self, status: str) -> None:
        self._status_filter = status
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent) -> bool:
        model = self.sourceModel()
        entry: KernelEntry | None = model.data(model.index(source_row, 0), Qt.ItemDataRole.UserRole)
        if entry is None:
            return True

        if self._family_filter and entry.family.value != self._family_filter:
            return False
        if self._status_filter and entry.status.name.lower() != self._status_filter:
            return False

        # Text filter (from QSortFilterProxyModel)
        return super().filterAcceptsRow(source_row, source_parent)


class KernelView(QWidget):
    """
    A complete kernel list widget: filter bar + table + context menu.
    Emits signals when the user requests actions.
    """

    install_requested = Signal(object)  # KernelEntry
    remove_requested = Signal(object)
    hold_requested = Signal(object)
    unhold_requested = Signal(object)
    note_requested = Signal(object)
    refresh_requested = Signal()

    def __init__(
        self,
        family_filter: str = "",  # lock to a specific family (for tabs)
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._family_lock = family_filter
        self._model = KernelTableModel()
        self._proxy = KernelFilterProxy()
        self._proxy.setSourceModel(self._model)
        if family_filter:
            self._proxy.set_family(family_filter)
        self._setup_ui()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_entries(self, entries: list[KernelEntry]) -> None:
        self._model.set_entries(entries)

    def selected_entry(self) -> KernelEntry | None:
        indexes = self._table.selectionModel().selectedRows()
        if not indexes:
            return None
        proxy_idx = indexes[0]
        source_idx = self._proxy.mapToSource(proxy_idx)
        return self._model.entry_at(source_idx.row())

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Filter bar
        filter_bar = QHBoxLayout()

        self._search = QLineEdit()
        self._search.setPlaceholderText("Filter kernels…")
        self._search.textChanged.connect(self._proxy.setFilterFixedString)
        filter_bar.addWidget(self._search, stretch=3)

        if not self._family_lock:
            filter_bar.addWidget(QLabel("Family:"))
            self._family_combo = QComboBox()
            self._family_combo.addItem("All", "")
            for f in KernelFamily:
                self._family_combo.addItem(f.value.title(), f.value)
            self._family_combo.currentIndexChanged.connect(self._on_family_changed)
            filter_bar.addWidget(self._family_combo)

        filter_bar.addWidget(QLabel("Status:"))
        self._status_combo = QComboBox()
        self._status_combo.addItem("All", "")
        for s in KernelStatus:
            self._status_combo.addItem(s.name.lower(), s.name.lower())
        self._status_combo.currentIndexChanged.connect(self._on_status_changed)
        filter_bar.addWidget(self._status_combo)

        layout.addLayout(filter_bar)

        # Table
        self._table = QTableView()
        self._table.setModel(self._proxy)
        self._table.setSortingEnabled(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._table.setAlternatingRowColors(True)
        self._table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self._table.horizontalHeader().setStretchLastSection(True)
        self._table.sortByColumn(0, Qt.SortOrder.DescendingOrder)
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._show_context_menu)
        self._table.doubleClicked.connect(self._on_double_click)
        layout.addWidget(self._table)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_family_changed(self, idx: int) -> None:
        value = self._family_combo.itemData(idx)
        self._proxy.set_family(value or "")

    def _on_status_changed(self, idx: int) -> None:
        value = self._status_combo.itemData(idx)
        self._proxy.set_status(value or "")

    def _on_double_click(self, index) -> None:
        entry = self.selected_entry()
        if entry and not entry.is_installed:
            self.install_requested.emit(entry)

    def _show_context_menu(self, pos) -> None:
        entry = self.selected_entry()
        if entry is None:
            return

        menu = QMenu(self)

        if not entry.is_installed:
            act = menu.addAction("Install")
            act.triggered.connect(lambda: self.install_requested.emit(entry))
        else:
            if not entry.is_running:
                act = menu.addAction("Remove")
                act.triggered.connect(lambda: self.remove_requested.emit(entry))

            if entry.held:
                act = menu.addAction("Unhold")
                act.triggered.connect(lambda: self.unhold_requested.emit(entry))
            else:
                act = menu.addAction("Hold / Pin")
                act.triggered.connect(lambda: self.hold_requested.emit(entry))

        menu.addSeparator()
        act = menu.addAction("Edit Note…")
        act.triggered.connect(lambda: self.note_requested.emit(entry))

        if entry.source_url and entry.source_url.startswith("http"):
            act = menu.addAction("Open PPA Page")
            act.triggered.connect(lambda: self._open_url(entry.source_url))

        menu.exec(self._table.viewport().mapToGlobal(pos))

    @staticmethod
    def _open_url(url: str) -> None:
        import shutil
        import subprocess

        for browser in ("xdg-open", "open"):
            if shutil.which(browser):
                subprocess.Popen([browser, url])
                return
