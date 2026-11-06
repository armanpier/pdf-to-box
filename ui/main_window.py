"""
Main application window.
Left sidebar: numbered step nav buttons.
Right: QStackedWidget swapping between step panels.
"""
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QStackedWidget, QLabel, QStatusBar, QFrame,
)
from PyQt6.QtCore import Qt, QSize, QTimer
from PyQt6.QtGui import QFont, QCursor

from core.session import AppSession
from core.ai_status import get_ai_connection_summary
from ui.step0_input   import Step0Input
from ui.step1_align   import Step1Align
from ui.step2_verify  import Step2Verify
from ui.step3_boxtype import Step3BoxType
from ui.step4_output  import Step4Output


_STEP_LABELS = ["① Input", "② Align", "③ Verify", "④ Map Faces", "⑤ Build"]
_STEP_TIPS   = [
    "Select PDF dieline and diffuse texture",
    "Align texture to PDF dieline",
    "Verify UV overlay before modelling",
    "Map dieline panels to 3D box faces and review dimensions",
    "Generate MaxScript and send to 3ds Max",
]


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("PDF to Box — 3ds Max Packaging Builder")
        self.resize(1200, 750)
        self.setMinimumSize(900, 600)

        self._session = AppSession()
        self._current_step = 0

        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Left sidebar ──────────────────────────────────────────────────────
        sidebar = QWidget()
        sidebar.setFixedWidth(160)
        sidebar.setStyleSheet("background: #252526;")
        sv = QVBoxLayout(sidebar)
        sv.setContentsMargins(8, 16, 8, 16)
        sv.setSpacing(4)

        logo = QLabel("📦 PDF→Box")
        logo.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        logo.setStyleSheet("color: #f0a500; padding: 8px 0;")
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sv.addWidget(logo)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #444;")
        sv.addWidget(line)
        sv.addSpacing(6)

        # AI Status Card in Sidebar
        self._ai_card = QFrame()
        self._ai_card.setStyleSheet("""
            QFrame {
                background: #1e261e;
                border: 1px solid #388e3c;
                border-radius: 6px;
                padding: 4px;
            }
        """)
        self._ai_card.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        ai_card_lay = QVBoxLayout(self._ai_card)
        ai_card_lay.setContentsMargins(6, 4, 6, 4)
        ai_card_lay.setSpacing(2)

        self._ai_header_lbl = QLabel("🟢 AI Connected")
        self._ai_header_lbl.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        self._ai_header_lbl.setStyleSheet("color: #4caf50;")
        self._ai_header_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ai_card_lay.addWidget(self._ai_header_lbl)

        self._ai_detail_lbl = QLabel("Bionic (qwen3.5)")
        self._ai_detail_lbl.setFont(QFont("Segoe UI", 7))
        self._ai_detail_lbl.setStyleSheet("color: #a5d6a7;")
        self._ai_detail_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ai_card_lay.addWidget(self._ai_detail_lbl)

        sv.addWidget(self._ai_card)
        sv.addSpacing(8)

        self._step_btns: list[QPushButton] = []
        for i, (lbl, tip) in enumerate(zip(_STEP_LABELS, _STEP_TIPS)):
            btn = QPushButton(lbl)
            btn.setToolTip(tip)
            btn.setCheckable(True)
            btn.setFixedHeight(40)
            btn.setProperty("step_idx", i)
            btn.clicked.connect(self._on_step_btn)
            btn.setEnabled(i == 0)
            sv.addWidget(btn)
            self._step_btns.append(btn)

        sv.addStretch()

        line2 = QFrame()
        line2.setFrameShape(QFrame.Shape.HLine)
        line2.setStyleSheet("color: #444;")
        sv.addWidget(line2)

        self._settings_btn = QPushButton("⚙ Settings")
        self._settings_btn.setToolTip("Box Orientation & Lid Settings (Step 4)")
        self._settings_btn.setFixedHeight(34)
        self._settings_btn.clicked.connect(self._open_settings)
        sv.addWidget(self._settings_btn)

        layout.addWidget(sidebar)

        # ── Content area ──────────────────────────────────────────────────────
        self._stack = QStackedWidget()

        self._steps: list[QWidget] = []
        creators = [
            lambda: Step0Input(self._session),
            lambda: Step1Align(self._session),
            lambda: Step2Verify(self._session),
            lambda: Step3BoxType(self._session),
            lambda: Step4Output(self._session),
        ]
        for fn in creators:
            w = fn()
            self._stack.addWidget(w)
            self._steps.append(w)

        # Wire step_done signals
        self._steps[0].step_done.connect(lambda: self._advance(1))
        self._steps[1].step_done.connect(lambda: self._advance(2))
        self._steps[2].step_done.connect(lambda: self._advance(3))
        self._steps[3].step_done.connect(lambda: self._advance(4))
        self._steps[4].step_done.connect(lambda: self._advance(0))

        layout.addWidget(self._stack)

        # ── Status bar ────────────────────────────────────────────────────────
        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._status.showMessage("Ready — select a PDF and texture to begin.")

        self._status_ai_lbl = QLabel("Checking AI...")
        self._status_ai_lbl.setStyleSheet("padding: 0 10px; font-weight: bold; font-size: 9pt;")
        self._status.addPermanentWidget(self._status_ai_lbl)

        # AI Connection check timer
        self._ai_timer = QTimer(self)
        self._ai_timer.setInterval(6000)
        self._ai_timer.timeout.connect(self._refresh_ai_status)
        self._ai_timer.start()
        QTimer.singleShot(150, self._refresh_ai_status)

        # Allow clicking sidebar AI card to force refresh
        self._ai_card.mousePressEvent = lambda e: self._refresh_ai_status()

        self._go_to_step(0)
        self._apply_stylesheet()

    # ── Navigation ────────────────────────────────────────────────────────────

    def _on_step_btn(self):
        btn = self.sender()
        idx = btn.property("step_idx")
        self._go_to_step(idx)

    def _advance(self, step: int):
        if step == 0:
            # "Start over" — reset session
            self._session = AppSession()
            for i, s in enumerate(self._steps):
                # Re-create steps with fresh session
                pass
            # Just go to step 0 visually
            self._go_to_step(0)
            for i in range(1, len(self._step_btns)):
                self._step_btns[i].setEnabled(False)
            return

        # Unlock next step button
        if step < len(self._step_btns):
            self._step_btns[step].setEnabled(True)
        self._go_to_step(step)

    def _go_to_step(self, idx: int):
        self._current_step = idx
        self._stack.setCurrentIndex(idx)
        for i, btn in enumerate(self._step_btns):
            btn.setChecked(i == idx)

        # Notify step that it's now visible
        step_widget = self._steps[idx]
        if hasattr(step_widget, "activate"):
            try:
                step_widget.activate()
            except Exception:
                pass

        self._status.showMessage(f"Step {idx + 1}/5 — {_STEP_TIPS[idx]}")

    def _open_settings(self):
        """Navigate to Step 3 Face Mapping & Settings where orientation controls reside."""
        if self._step_btns[3].isEnabled():
            self._go_to_step(3)
        else:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(
                self,
                "Settings & Orientation",
                "Orientation settings are available in Step ④ (Map Faces).\n\n"
                "Please load input files (Step ①) and complete alignment to configure box orientation."
            )

    # ── AI Status Monitor ─────────────────────────────────────────────────────

    def _refresh_ai_status(self):
        try:
            info = get_ai_connection_summary()
            if info.get("connected"):
                bionic = info.get("bionic", {})
                ollama = info.get("ollama", {})
                if bionic.get("online"):
                    svc = bionic.get("display_name", "Bionic")
                    lat = bionic.get("latency_ms", 0)
                    detail = f"{svc} ({lat}ms)"
                elif ollama.get("online"):
                    svc = ollama.get("display_name", "Ollama")
                    lat = ollama.get("latency_ms", 0)
                    detail = f"{svc} ({lat}ms)"
                else:
                    detail = "Local AI Online"

                self._ai_card.setStyleSheet("""
                    QFrame {
                        background: #1c2b1e;
                        border: 1px solid #4caf50;
                        border-radius: 6px;
                        padding: 4px;
                    }
                """)
                self._ai_header_lbl.setText("🟢 AI Connected")
                self._ai_header_lbl.setStyleSheet("color: #81c784; font-weight: bold;")
                self._ai_detail_lbl.setText(detail)
                self._status_ai_lbl.setText(f"🟢 AI: {detail}")
                self._status_ai_lbl.setStyleSheet("color: #81c784; padding: 0 12px; font-weight: bold;")
                self._ai_card.setToolTip(f"Local AI Active:\n{info.get('summary')}\nClick to re-check connection.")
            else:
                self._ai_card.setStyleSheet("""
                    QFrame {
                        background: #2b1e1e;
                        border: 1px solid #e57373;
                        border-radius: 6px;
                        padding: 4px;
                    }
                """)
                self._ai_header_lbl.setText("🔴 AI Offline")
                self._ai_header_lbl.setStyleSheet("color: #e57373; font-weight: bold;")
                self._ai_detail_lbl.setText("Start Bionic (:1234)")
                self._status_ai_lbl.setText("🔴 AI Offline")
                self._status_ai_lbl.setStyleSheet("color: #e57373; padding: 0 12px; font-weight: bold;")
                self._ai_card.setToolTip("Start Bionic (:1234) or Ollama (:11434) for AI face detection.\nClick to re-check connection.")
        except Exception as e:
            pass

    # ── Stylesheet ────────────────────────────────────────────────────────────

    def _apply_stylesheet(self):
        self.setStyleSheet("""
        QMainWindow { background: #1e1e1e; }
        QWidget { color: #d4d4d4; font-family: 'Segoe UI'; font-size: 10pt; }
        QPushButton {
            background: #3c3c3c; border: 1px solid #555; border-radius: 4px;
            padding: 4px 10px; color: #d4d4d4;
        }
        QPushButton:hover   { background: #505050; }
        QPushButton:checked { background: #007acc; color: white; border-color: #007acc; }
        QPushButton:disabled { color: #666; background: #2a2a2a; }
        QGroupBox {
            border: 1px solid #555; border-radius: 4px; margin-top: 8px;
            padding-top: 8px; font-weight: bold;
        }
        QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }
        QLineEdit, QDoubleSpinBox, QTextEdit {
            background: #2d2d2d; border: 1px solid #555; border-radius: 3px;
            padding: 3px 6px;
        }
        QSplitter::handle { background: #3c3c3c; }
        QProgressBar {
            border: 1px solid #555; border-radius: 3px; background: #2d2d2d;
            text-align: center;
        }
        QProgressBar::chunk { background: #007acc; border-radius: 2px; }
        QStatusBar { background: #1a1a1a; border-top: 1px solid #444; }
        """)
