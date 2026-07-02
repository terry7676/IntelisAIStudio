from __future__ import annotations

import argparse
from pathlib import Path

from terrygpt.core.manager import CoreManager


def initialize_core(config_path: Path | None = None) -> CoreManager:
    core = CoreManager.build(config_path=config_path)
    core.initialize()
    core.start()
    return core


def run_desktop(config_path: Path | None = None) -> int:
    try:
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QPixmap
        from PySide6.QtWidgets import QApplication, QSplashScreen
    except ModuleNotFoundError as exc:
        raise SystemExit("PySide6 is not installed. Run: python -m pip install -e .") from exc

    from terrygpt.gui.main_window import TerryMainWindow

    app = QApplication.instance() or QApplication([])

    splash_pixmap = QPixmap(520, 220)
    splash_pixmap.fill(Qt.GlobalColor.black)
    splash = QSplashScreen(splash_pixmap)
    splash.showMessage("Starting TerryGPT Core Engine...", Qt.AlignmentFlag.AlignCenter, Qt.GlobalColor.white)
    splash.show()
    app.processEvents()

    core = initialize_core(config_path)
    window = TerryMainWindow(core)
    window.show()
    splash.finish(window)

    try:
        return app.exec()
    finally:
        core.stop()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python main.py")
    parser.add_argument("--config", help="Path to a TOML config file.")
    parser.add_argument("--no-gui", action="store_true", help="Initialize the core engine without opening the desktop UI.")
    args = parser.parse_args(argv)

    config_path = Path(args.config) if args.config else None
    if args.no_gui:
        core = initialize_core(config_path)
        core.stop()
        print("TerryGPT Core Engine initialized successfully.")
        return 0
    return run_desktop(config_path)

