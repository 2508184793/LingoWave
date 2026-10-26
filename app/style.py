STYLE = """
QWidget { background:#0e151c; color:#e7edf2; font-family:'Microsoft YaHei UI','Segoe UI'; font-size:13px; }
QMainWindow { background:#0e151c; }
QLabel { background:transparent; }
QLabel#muted { color:#899aa9; font-size:12px; }
QLabel#brand { color:#f2f7f8; font-family:'Segoe UI'; font-size:26px; font-weight:700; }
QLabel#hero { font-size:29px; font-weight:700; color:#f2f7f8; }
QLabel#sectionTitle { font-size:17px; font-weight:600; }
QLabel#eyebrow { color:#79d9ba; font-family:'Segoe UI'; font-size:11px; letter-spacing:2px; }
QLabel#badge { background:#18382f; color:#8ae1bf; border-radius:11px; padding:5px 12px; font-size:11px; }
QFrame#card { background:#151f29; border:1px solid #263440; border-radius:14px; }
QFrame#card QLabel, QFrame#card QCheckBox { background:transparent; }
QFrame#rail { background:#101a23; border-right:1px solid #23313d; }
QPushButton { background:#202e3a; border:1px solid #344654; border-radius:8px; padding:9px 15px; color:#dce7ed; }
QPushButton:hover { background:#2a3d4b; border-color:#56747f; }
QPushButton:pressed { background:#16242e; }
QPushButton:disabled { color:#586a78; background:#19232c; border-color:#24333e; }
QPushButton#primary { background:#8de0bb; color:#10231c; border:none; font-weight:700; font-size:15px; padding:13px; }
QPushButton#primary:hover { background:#a4edcd; }
QPushButton#primary:disabled { background:#314c42; color:#7f9a8e; }
QPushButton#quiet { background:transparent; border:1px solid #2d3d49; padding:7px 12px; }
QComboBox,QLineEdit,QSpinBox,QDoubleSpinBox { background:#101a23; border:1px solid #344654; border-radius:7px; padding:7px 10px; min-height:20px; selection-background-color:#376955; }
QComboBox:focus,QLineEdit:focus { border-color:#8de0bb; }
QComboBox::drop-down { border:none; width:22px; }
QComboBox QAbstractItemView { background:#1b2a36; selection-background-color:#305b4c; padding:4px; }
QCheckBox { spacing:8px; }
QCheckBox::indicator { width:16px; height:16px; border:1px solid #5e7584; border-radius:4px; background:#101a23; }
QCheckBox::indicator:checked { background:#8de0bb; border-color:#8de0bb; image:none; }
QProgressBar { background:#0c141c; border:none; border-radius:4px; min-height:7px; max-height:7px; }
QProgressBar::chunk { background:#8de0bb; border-radius:4px; }
QListWidget { background:transparent; border:none; outline:none; }
QListWidget::item { background:#151f29; border:1px solid #263440; border-radius:10px; margin-bottom:8px; }
QListWidget::item:selected { border-color:#5f9f88; }
QScrollArea { border:none; }
QScrollBar:vertical { background:transparent; width:7px; }
QScrollBar::handle:vertical { background:#344654; border-radius:3px; min-height:28px; }
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical { height:0; }
QGroupBox { border:1px solid #2a3b48; border-radius:10px; margin-top:16px; padding:18px 12px 12px; font-weight:600; }
QGroupBox::title { subcontrol-origin:margin; left:14px; padding:0 5px; color:#8de0bb; }
QToolTip { background:#213440; color:#eef5f4; border:1px solid #4b6a70; }
QStatusBar { background:#101a23; color:#8fa2af; font-size:11px; }
"""
