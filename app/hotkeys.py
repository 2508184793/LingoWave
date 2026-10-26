from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter
from PySide6.QtGui import QKeySequence, QShortcut


class GlobalHotkeys(QAbstractNativeEventFilter):
    def __init__(self, app, window, callbacks):
        super().__init__()
        self.app = app
        self.callbacks = callbacks
        self.registered = []
        self.shortcuts = []
        self.failed = []
        for number, (key, callback) in enumerate(callbacks.items(), 1):
            if sys.platform == "win32" and ctypes.windll.user32.RegisterHotKey(None, 0x4C00 + number, 0x4003, key):
                self.registered.append(0x4C00 + number)
            else:
                shortcut = QShortcut(QKeySequence(f"Ctrl+Alt+F{key - 0x6F}"), window)
                shortcut.activated.connect(callback)
                self.shortcuts.append(shortcut)
                self.failed.append(key)
        app.installNativeEventFilter(self)

    def nativeEventFilter(self, event_type, message):
        if sys.platform == "win32":
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == 0x0312 and msg.wParam in self.registered:
                index = msg.wParam - 0x4C01
                list(self.callbacks.values())[index]()
                return True, 0
        return False, 0

    def close(self):
        self.app.removeNativeEventFilter(self)
        for number in self.registered:
            ctypes.windll.user32.UnregisterHotKey(None, number)
