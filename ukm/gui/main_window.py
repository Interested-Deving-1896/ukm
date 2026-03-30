"""
Main application window.

Layout:
  ┌─────────────────────────────────────────────────────┐
  │  Toolbar: [Refresh] [Install] [Remove] [Hold] ...   │
  ├─────────────────────────────────────────────────────┤
  │  Status bar: distro | arch | running kernel         │
  ├─────────────────────────────────────────────────────┤
  │  Tab bar:                                           │
  │  [ All ] [ Mainline PPA ] [ XanMod ] [ Liquorix ]  │
  │  [ Distro ] [ Gentoo* ] [ Local ]                  │
  │                                                     │
  │  ┌─ Filter bar ──────────────────────────────────┐  │
  │  │ [search…] Family▾ Status▾                     │  │
  │  └───────────────────────────────────────────────┘  │
  │  ┌─ Kernel table ────────────────────────────────┐  │
  │  │ Version  Flavor  Family  Arch  Status  …      │  │
  │  └───────────────────────────────────────────────┘  │
  ├─────────────────────────────────────────────────────┤
  │  [ Details ▾ ]  [Clear]                             │
  │  log output…                                        │
  └─────────────────────────────────────────────────────┘

* Gentoo tab only shown when portage backend is active.
"""

from __future__ import annotations

from ukm import __version__
from ukm.core.backends.portage import PortageBackend
from ukm.core.kernel import KernelEntry, KernelFamily
from ukm.core.manager import KernelManager
from ukm.core.providers.gentoo import GentooProvider
from ukm.core.system import system_info
from ukm.gui.widgets.changelog_panel import ChangelogPanel
from ukm.gui.widgets.gentoo_compile_dialog import GentooCompileDialog
from ukm.gui.widgets.kernel_view import KernelView
from ukm.gui.widgets.log_panel import LogPanel
from ukm.gui.widgets.note_dialog import NoteDialog
from ukm.qt import (
    QAction,
    QApplication,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QTabWidget,
    QThread,
    QToolBar,
    QVBoxLayout,
    QWidget,
    Qt,
    Signal,
    Slot,
)


# ---------------------------------------------------------------------------
# Background worker for long-running operations
# ---------------------------------------------------------------------------


class _OperationWorker(QThread):
    line_ready = Signal(str)
    finished_ok = Signal(str)  # success message
    finished_err = Signal(str)  # error message

    def __init__(self, gen_fn) -> None:
        super().__init__()
        self._gen_fn = gen_fn  # callable that returns an iterator of log lines

    def run(self) -> None:
        try:
            for line in self._gen_fn():
                self.line_ready.emit(line)
            self.finished_ok.emit("Done.")
        except Exception as e:
            self.finished_err.emit(str(e))


class _RefreshWorker(QThread):
    finished = Signal(list)  # list[KernelEntry]
    error = Signal(str)

    def __init__(self, manager: KernelManager, refresh: bool = False) -> None:
        super().__init__()
        self._manager = manager
        self._refresh = refresh

    def run(self) -> None:
        try:
            entries = self._manager.list_all(refresh=self._refresh)
            self.finished.emit(entries)
        except Exception as e:
            self.error.emit(str(e))


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self._manager = KernelManager()
        self._entries: list[KernelEntry] = []
        self._worker: QThread | None = None

        self.setWindowTitle(f"ukm — Universal Kernel Manager  v{__version__}")
        self.setMinimumSize(900, 600)
        self.resize(1100, 700)

        self._setup_ui()
        self._setup_toolbar()
        self._setup_statusbar()
        self._check_secure_boot()
        self._refresh(force=False)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _setup_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(0)

        # Outer horizontal splitter: [tabs+log | changelog panel]
        h_splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(h_splitter)

        # Left side: vertical splitter (tabs on top, log on bottom)
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)
        splitter = QSplitter(Qt.Orientation.Vertical)
        left_layout.addWidget(splitter)
        h_splitter.addWidget(left_widget)

        # Changelog panel on the right
        self._changelog = ChangelogPanel()
        self._changelog.setMinimumWidth(260)
        self._changelog.setMaximumWidth(480)
        h_splitter.addWidget(self._changelog)
        h_splitter.setStretchFactor(0, 3)
        h_splitter.setStretchFactor(1, 1)

        # Tab widget
        self._tabs = QTabWidget()
        self._tabs.setDocumentMode(True)
        splitter.addWidget(self._tabs)

        # "All" tab — unified list with family + status filters
        self._all_view = KernelView(family_filter="")
        self._tabs.addTab(self._all_view, "All")
        self._connect_view(self._all_view)

        # Per-family tabs
        self._family_views: dict[str, KernelView] = {}
        tab_families = [
            (KernelFamily.MAINLINE, "Mainline PPA"),
            (KernelFamily.XANMOD, "XanMod"),
            (KernelFamily.LIQUORIX, "Liquorix"),
            (KernelFamily.DISTRO, "Distro"),
            (KernelFamily.LOCAL, "Local"),
        ]
        # AUR tab — shown on Arch systems; reuses DISTRO family filtered by provider
        from ukm.core.system import PackageManagerKind

        if system_info().package_manager == PackageManagerKind.PACMAN:
            aur_view = KernelView(family_filter="")
            self._tabs.addTab(aur_view, "AUR")
            self._aur_view = aur_view
            self._connect_view(aur_view)
        for family, label in tab_families:
            view = KernelView(family_filter=family.value)
            self._tabs.addTab(view, label)
            self._family_views[family.value] = view
            self._connect_view(view)

        # Gentoo tab — only if portage backend
        from ukm.core.backends import get_backend

        if isinstance(get_backend(), PortageBackend):
            gentoo_view = KernelView(family_filter=KernelFamily.GENTOO.value)
            self._tabs.insertTab(
                self._tabs.count() - 1,  # before Local
                gentoo_view,
                "Gentoo",
            )
            self._family_views[KernelFamily.GENTOO.value] = gentoo_view
            self._connect_view(gentoo_view)

        # Log panel
        self._log = LogPanel()
        self._log.setMaximumHeight(220)
        splitter.addWidget(self._log)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

    def _setup_toolbar(self) -> None:
        tb = QToolBar("Main")
        tb.setMovable(False)
        self.addToolBar(tb)

        self._act_refresh = QAction("↺  Refresh", self)
        self._act_refresh.setToolTip("Re-download kernel index and refresh list")
        self._act_refresh.triggered.connect(lambda: self._refresh(force=True))
        tb.addAction(self._act_refresh)

        tb.addSeparator()

        self._act_install = QAction("⬇  Install", self)
        self._act_install.setToolTip("Install selected kernel")
        self._act_install.triggered.connect(self._on_install)
        tb.addAction(self._act_install)

        self._act_remove = QAction("✕  Remove", self)
        self._act_remove.setToolTip("Remove selected kernel")
        self._act_remove.triggered.connect(self._on_remove)
        tb.addAction(self._act_remove)

        tb.addSeparator()

        self._act_hold = QAction("🔒  Hold", self)
        self._act_hold.setToolTip("Pin selected kernel (prevent auto-upgrade/removal)")
        self._act_hold.triggered.connect(self._on_hold)
        tb.addAction(self._act_hold)

        self._act_unhold = QAction("🔓  Unhold", self)
        self._act_unhold.setToolTip("Release held kernel")
        self._act_unhold.triggered.connect(self._on_unhold)
        tb.addAction(self._act_unhold)

        tb.addSeparator()

        self._act_remove_old = QAction("🗑  Remove Old", self)
        self._act_remove_old.setToolTip("Remove all old kernels, keeping running + most recent")
        self._act_remove_old.triggered.connect(self._on_remove_old)
        tb.addAction(self._act_remove_old)

        self._act_local = QAction("📂  Install File…", self)
        self._act_local.setToolTip("Install a local kernel package file")
        self._act_local.triggered.connect(self._on_install_local)
        tb.addAction(self._act_local)

        # Gentoo compile button — only shown on Gentoo
        from ukm.core.backends import get_backend

        if isinstance(get_backend(), PortageBackend):
            tb.addSeparator()
            self._act_compile = QAction("⚙  Compile…", self)
            self._act_compile.setToolTip("Configure and compile a Gentoo kernel from source")
            self._act_compile.triggered.connect(self._on_gentoo_compile)
            tb.addAction(self._act_compile)

    def _setup_statusbar(self) -> None:
        sb = self.statusBar()
        info = system_info()
        from ukm.core import dkms

        self._status_distro = QLabel(f"  {info.distro.name}")
        self._status_arch = QLabel(f"  {info.arch}")
        self._status_kernel = QLabel(f"  Running: {info.running_kernel}")
        self._status_pm = QLabel(f"  {info.package_manager.value}")
        self._status_dkms = QLabel(f"  DKMS: {dkms.status_summary()}")
        for lbl in (
            self._status_distro,
            self._status_arch,
            self._status_kernel,
            self._status_pm,
            self._status_dkms,
        ):
            sb.addPermanentWidget(lbl)

    # ------------------------------------------------------------------
    # View signal wiring
    # ------------------------------------------------------------------

    def _connect_view(self, view: KernelView) -> None:
        view.install_requested.connect(self._do_install)
        view.remove_requested.connect(self._do_remove)
        view.hold_requested.connect(self._do_hold)
        view.unhold_requested.connect(self._do_unhold)
        view.note_requested.connect(self._do_note)
        view.refresh_requested.connect(lambda: self._refresh(force=True))
        # Wire table selection → changelog panel
        view._table.selectionModel().currentRowChanged.connect(
            lambda cur, _prev: self._on_selection_changed(view)
        )

    # ------------------------------------------------------------------
    # Toolbar action handlers
    # ------------------------------------------------------------------

    def _on_selection_changed(self, view: KernelView) -> None:
        entry = view.selected_entry()
        if entry:
            self._changelog.show_entry(entry)
        else:
            self._changelog.clear()

    def _on_install(self) -> None:
        entry = self._current_view().selected_entry()
        if entry:
            self._do_install(entry)

    def _on_remove(self) -> None:
        entry = self._current_view().selected_entry()
        if entry:
            self._do_remove(entry)

    def _on_hold(self) -> None:
        entry = self._current_view().selected_entry()
        if entry:
            self._do_hold(entry)

    def _on_unhold(self) -> None:
        entry = self._current_view().selected_entry()
        if entry:
            self._do_unhold(entry)

    def _on_remove_old(self) -> None:
        reply = QMessageBox.question(
            self,
            "Remove Old Kernels",
            "Remove all installed kernels except the running one and the most recent?\n"
            "Locked kernels will be preserved.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._run_operation(lambda: self._manager.remove_old(), "Removing old kernels…")

    def _on_install_local(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select kernel package",
            "",
            "Packages (*.deb *.rpm *.pkg.tar.* *.apk);;All files (*)",
        )
        if not path:
            return
        from ukm.core.backends import get_backend
        from ukm.core.providers.local_file import LocalFileProvider

        provider = LocalFileProvider(get_backend())
        entry = provider.entry_from_path(path, system_info().arch)
        self._do_install(entry)

    def _on_gentoo_compile(self) -> None:
        provider = next((p for p in self._manager.providers if isinstance(p, GentooProvider)), None)
        if provider is None:
            QMessageBox.warning(self, "Gentoo", "Gentoo provider not available.")
            return
        dlg = GentooCompileDialog(provider, self)
        dlg.exec()

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def _do_install(self, entry: KernelEntry) -> None:
        if entry.is_installed:
            QMessageBox.information(
                self, "Already Installed", f"Kernel {entry.display_name} is already installed."
            )
            return
        reply = QMessageBox.question(
            self,
            "Install Kernel",
            f"Install <b>{entry.display_name}</b> from <i>{entry.provider_id}</i>?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._run_operation(
                lambda: self._manager.install(entry), f"Installing {entry.display_name}…"
            )

    def _do_remove(self, entry: KernelEntry) -> None:
        if entry.is_running:
            QMessageBox.warning(
                self, "Cannot Remove", "Cannot remove the currently running kernel."
            )
            return
        if entry.held:
            QMessageBox.warning(
                self, "Kernel Locked", f"{entry.display_name} is locked. Unhold it first."
            )
            return
        reply = QMessageBox.question(
            self,
            "Remove Kernel",
            f"Remove <b>{entry.display_name}</b>?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._run_operation(
                lambda: self._manager.remove(entry), f"Removing {entry.display_name}…"
            )

    def _do_hold(self, entry: KernelEntry) -> None:
        rc, out, err = self._manager.hold(entry)
        if out:
            self._log.append(out)
        if err:
            self._log.append(err)
        if rc == 0:
            self._log.append(f"✓ {entry.display_name} held.\n")
            self._refresh(force=False)
        else:
            QMessageBox.warning(self, "Hold Failed", err or "Unknown error")

    def _do_unhold(self, entry: KernelEntry) -> None:
        rc, out, err = self._manager.unhold(entry)
        if out:
            self._log.append(out)
        if err:
            self._log.append(err)
        if rc == 0:
            self._log.append(f"✓ {entry.display_name} unheld.\n")
            self._refresh(force=False)
        else:
            QMessageBox.warning(self, "Unhold Failed", err or "Unknown error")

    def _do_note(self, entry: KernelEntry) -> None:
        dlg = NoteDialog(entry, self)
        if dlg.exec() == NoteDialog.DialogCode.Accepted:
            self._manager.set_note(entry, dlg.note_text())
            self._refresh(force=False)

    # ------------------------------------------------------------------
    # Background operation runner
    # ------------------------------------------------------------------

    def _run_operation(self, gen_fn, status_msg: str) -> None:
        if self._worker and self._worker.isRunning():
            QMessageBox.warning(self, "Busy", "Another operation is in progress.")
            return

        self._set_busy(True)
        self._log.show_panel()
        self._log.append(f"\n{status_msg}\n")
        self.statusBar().showMessage(status_msg)

        self._worker = _OperationWorker(gen_fn)
        self._worker.line_ready.connect(self._log.append)
        self._worker.finished_ok.connect(self._on_operation_done)
        self._worker.finished_err.connect(self._on_operation_error)
        self._worker.start()

    @Slot(str)
    def _on_operation_done(self, msg: str) -> None:
        self._log.append(f"\n✓ {msg}\n")
        self.statusBar().showMessage("Ready", 3000)
        self._set_busy(False)
        self._refresh(force=False)

    @Slot(str)
    def _on_operation_error(self, msg: str) -> None:
        self._log.append(f"\n✗ Error: {msg}\n")
        self.statusBar().showMessage("Error — see log", 5000)
        self._set_busy(False)
        QMessageBox.critical(self, "Operation Failed", msg)

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------

    def _refresh(self, force: bool = False) -> None:
        self._set_busy(True)
        self.statusBar().showMessage("Loading kernel list…")
        worker = _RefreshWorker(self._manager, refresh=force)
        worker.finished.connect(self._on_refresh_done)
        worker.error.connect(self._on_refresh_error)
        # Keep reference so it isn't GC'd
        self._refresh_worker = worker
        worker.start()

    @Slot(list)
    def _on_refresh_done(self, entries: list[KernelEntry]) -> None:
        self._entries = entries
        self._all_view.set_entries(entries)
        for family_val, view in self._family_views.items():
            view.set_entries([e for e in entries if e.family.value == family_val])
        count = len(entries)
        installed = sum(1 for e in entries if e.is_installed)
        self.statusBar().showMessage(f"Ready — {count} kernels ({installed} installed)", 5000)
        self._set_busy(False)

    @Slot(str)
    def _on_refresh_error(self, msg: str) -> None:
        self.statusBar().showMessage(f"Refresh error: {msg}", 8000)
        self._set_busy(False)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _current_view(self) -> KernelView:
        widget = self._tabs.currentWidget()
        if isinstance(widget, KernelView):
            return widget
        return self._all_view

    def _set_busy(self, busy: bool) -> None:
        for action in (
            self._act_refresh,
            self._act_install,
            self._act_remove,
            self._act_hold,
            self._act_unhold,
            self._act_remove_old,
            self._act_local,
        ):
            action.setEnabled(not busy)
        if busy:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        else:
            QApplication.restoreOverrideCursor()

    def _check_secure_boot(self) -> None:
        warn = self._manager.secure_boot_warning()
        if warn:
            QMessageBox.warning(self, "Secure Boot Detected", warn)
