DARK_STYLESHEET = """
QMainWindow, QWidget {
    background: #101419;
    color: #d7dde5;
    font-family: Segoe UI, Arial, sans-serif;
    font-size: 13px;
}
QListWidget#Navigation {
    background: #0b0f14;
    border: none;
    padding: 8px;
}
QListWidget#Navigation::item {
    padding: 10px 12px;
    border-radius: 4px;
}
QListWidget#Navigation::item:selected {
    background: #1f6feb;
    color: white;
}
QTabWidget::pane {
    border: 1px solid #26313d;
}
QTabBar::tab {
    background: #151b22;
    color: #b8c1cc;
    padding: 8px 14px;
    border: 1px solid #26313d;
}
QTabBar::tab:selected {
    background: #1d2630;
    color: #ffffff;
}
QPlainTextEdit, QTextEdit {
    background: #0d1117;
    color: #d7dde5;
    border: 1px solid #26313d;
    border-radius: 4px;
    padding: 8px;
}
QPushButton {
    background: #1f6feb;
    color: white;
    border: none;
    border-radius: 4px;
    padding: 8px 12px;
}
QPushButton:hover {
    background: #2f81f7;
}
QDockWidget {
    titlebar-close-icon: none;
    titlebar-normal-icon: none;
}
QLabel#PageTitle {
    font-size: 24px;
    font-weight: 700;
    padding: 8px 0;
}
QLabel#MutedText {
    color: #8b949e;
    font-size: 14px;
}
QStatusBar {
    background: #0b0f14;
    color: #8b949e;
}
"""

