"""
GUI entry point.

    ukm-gui
    UKM_QT=PyQt6 ukm-gui
"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    from ukm.qt import QApplication
    from ukm.gui.main_window import MainWindow

    app = QApplication(argv or sys.argv)
    app.setApplicationName("ukm")
    app.setApplicationDisplayName("Universal Kernel Manager")
    app.setOrganizationName("ukm")

    # Apply a clean stylesheet
    app.setStyleSheet(_STYLESHEET)

    window = MainWindow()
    window.show()
    return app.exec()


_STYLESHEET = """
QMainWindow {
    background-color: #1e1e2e;
}
QWidget {
    background-color: #1e1e2e;
    color: #cdd6f4;
    font-size: 13px;
}
QToolBar {
    background-color: #181825;
    border-bottom: 1px solid #313244;
    spacing: 4px;
    padding: 2px 4px;
}
QToolBar QToolButton {
    background: transparent;
    border: none;
    padding: 4px 8px;
    border-radius: 4px;
}
QToolBar QToolButton:hover {
    background-color: #313244;
}
QTabWidget::pane {
    border: none;
    background-color: #1e1e2e;
}
QTabBar::tab {
    background-color: #181825;
    color: #a6adc8;
    padding: 6px 16px;
    border: none;
    border-bottom: 2px solid transparent;
}
QTabBar::tab:selected {
    color: #cdd6f4;
    border-bottom: 2px solid #89b4fa;
    background-color: #1e1e2e;
}
QTabBar::tab:hover {
    background-color: #313244;
}
QTableView {
    background-color: #1e1e2e;
    alternate-background-color: #181825;
    gridline-color: #313244;
    border: none;
    selection-background-color: #313244;
    selection-color: #cdd6f4;
}
QHeaderView::section {
    background-color: #181825;
    color: #a6adc8;
    padding: 4px 8px;
    border: none;
    border-right: 1px solid #313244;
    font-weight: bold;
}
QLineEdit {
    background-color: #313244;
    border: 1px solid #45475a;
    border-radius: 4px;
    padding: 4px 8px;
    color: #cdd6f4;
}
QLineEdit:focus {
    border-color: #89b4fa;
}
QComboBox {
    background-color: #313244;
    border: 1px solid #45475a;
    border-radius: 4px;
    padding: 4px 8px;
    color: #cdd6f4;
}
QComboBox::drop-down {
    border: none;
}
QPushButton {
    background-color: #313244;
    border: 1px solid #45475a;
    border-radius: 4px;
    padding: 5px 14px;
    color: #cdd6f4;
}
QPushButton:hover {
    background-color: #45475a;
}
QPushButton:pressed {
    background-color: #585b70;
}
QTextEdit {
    background-color: #11111b;
    color: #a6e3a1;
    border: none;
    font-family: monospace;
}
QStatusBar {
    background-color: #181825;
    color: #a6adc8;
    border-top: 1px solid #313244;
}
QSplitter::handle {
    background-color: #313244;
    height: 2px;
}
QScrollBar:vertical {
    background: #181825;
    width: 8px;
}
QScrollBar::handle:vertical {
    background: #45475a;
    border-radius: 4px;
    min-height: 20px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
"""


if __name__ == "__main__":
    sys.exit(main())
