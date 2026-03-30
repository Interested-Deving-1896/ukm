"""
Qt binding compatibility shim.

Selects PySide6 or PyQt6 based on the UKM_QT environment variable or
whichever binding is installed. All GUI modules import from here instead
of directly from PySide6/PyQt6, so swapping bindings requires no code changes.

    UKM_QT=PySide6 ukm-gui
    UKM_QT=PyQt6   ukm-gui

mypy cannot type-check both branches of the if/else simultaneously, so the
entire shim is excluded from strict type checking via the ignore comments.
"""

# mypy: ignore-errors

import importlib
import os

_PREFERENCE = os.environ.get("UKM_QT", "").strip()


def _try(binding: str) -> bool:
    try:
        importlib.import_module(binding)
        return True
    except ImportError:
        return False


if _PREFERENCE == "PyQt6":
    _BINDING = "PyQt6" if _try("PyQt6") else None
elif _PREFERENCE == "PySide6":
    _BINDING = "PySide6" if _try("PySide6") else None
else:
    if _try("PySide6"):
        _BINDING = "PySide6"
    elif _try("PyQt6"):
        _BINDING = "PyQt6"
    else:
        _BINDING = None

if _BINDING is None:
    raise ImportError(
        "No Qt binding found. Install PySide6 or PyQt6:\n"
        "  pip install PySide6\n"
        "  pip install PyQt6\n"
        "Set UKM_QT=PySide6 or UKM_QT=PyQt6 to force a specific binding."
    )

if _BINDING == "PySide6":
    from PySide6.QtCore import (  # noqa: F401
        Qt, QThread, QObject, Signal, Slot, QTimer, QSize,
        QSortFilterProxyModel, QAbstractTableModel,
        QModelIndex, QPersistentModelIndex,
    )
    from PySide6.QtGui import (  # noqa: F401
        QIcon, QColor, QFont, QStandardItemModel, QStandardItem,
        QKeySequence, QAction as QGuiAction,
    )
    from PySide6.QtWidgets import (  # noqa: F401
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QTabWidget, QTableView, QHeaderView, QLabel, QPushButton,
        QLineEdit, QComboBox, QCheckBox, QTextEdit, QSplitter,
        QStatusBar, QToolBar, QAction, QDialog, QDialogButtonBox,
        QMessageBox, QFileDialog, QProgressBar, QFrame, QSizePolicy,
        QAbstractItemView, QMenu, QSystemTrayIcon,
    )
    BINDING = "PySide6"

else:  # PyQt6
    from PyQt6.QtCore import (  # noqa: F401
        Qt, QThread, QObject, QTimer, QSize,
        QSortFilterProxyModel, QAbstractTableModel,
        QModelIndex, QPersistentModelIndex,
        pyqtSignal as Signal, pyqtSlot as Slot,
    )
    from PyQt6.QtGui import (  # noqa: F401
        QIcon, QColor, QFont, QStandardItemModel, QStandardItem,
        QKeySequence, QAction as QGuiAction,
    )
    from PyQt6.QtWidgets import (  # noqa: F401
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QTabWidget, QTableView, QHeaderView, QLabel, QPushButton,
        QLineEdit, QComboBox, QCheckBox, QTextEdit, QSplitter,
        QStatusBar, QToolBar, QAction, QDialog, QDialogButtonBox,
        QMessageBox, QFileDialog, QProgressBar, QFrame, QSizePolicy,
        QAbstractItemView, QMenu, QSystemTrayIcon,
    )
    BINDING = "PyQt6"
