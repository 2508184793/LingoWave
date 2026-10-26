from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from .config import DATA_DIR
from .style import STYLE
from .window import MainWindow


def main():
    parser = argparse.ArgumentParser(description="LingoWave 桌面实时翻译")
    parser.add_argument("--demo", action="store_true", help="启动后显示预设字幕演示，不调用 API")
    parser.add_argument("--smoke-test", action="store_true", help="渲染界面截图后退出")
    args = parser.parse_args()
    os.environ.setdefault("PYTHONUTF8", "1")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=DATA_DIR / "app.log", encoding="utf-8", level=logging.WARNING,
                        format="%(asctime)s %(levelname)s %(message)s")
    app = QApplication(sys.argv[:1])
    app.setApplicationName("LingoWave")
    app.setOrganizationName("LingoWave")
    app.setFont(QFont("Microsoft YaHei UI", 10))
    app.setStyleSheet(STYLE)
    window = MainWindow(test_mode=args.smoke_test)
    window.show()
    if args.demo or args.smoke_test:
        QTimer.singleShot(300, window.start_demo)
    if args.smoke_test:
        def snapshot():
            output = Path(__file__).resolve().parent.parent / "artifacts"
            output.mkdir(exist_ok=True)
            window.grab().save(str(output / "window.png"))
            window.overlay.grab().save(str(output / "overlay.png"))
            window.close()
            app.quit()
        QTimer.singleShot(1800, snapshot)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
