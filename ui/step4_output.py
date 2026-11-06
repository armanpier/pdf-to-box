"""
Step 4 – Generate MaxScript and build 3D box in Autodesk 3ds Max.
"""
import os
import time
import threading
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QGroupBox, QMessageBox, QSplitter,
)
from PyQt6.QtCore import pyqtSignal, Qt, QObject, pyqtSlot
from PyQt6.QtGui import QFont, QPixmap


class _BuildSignals(QObject):
    log_msg = pyqtSignal(str)
    build_finished = pyqtSignal(bool, str)


class Step4Output(QWidget):
    step_done = pyqtSignal()

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self._session = session
        self._signals = _BuildSignals()
        self._signals.log_msg.connect(self._log_line)
        self._signals.build_finished.connect(self._on_build_completed)
        self._build_thread = None
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 18, 24, 18)
        root.setSpacing(14)

        root.addWidget(QLabel("<h2>⑤ Build & Send to 3ds Max</h2>"))

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(4)

        # Left Column: Files status & Log
        left_pane = QWidget()
        left_lay = QVBoxLayout(left_pane)
        left_lay.setContentsMargins(0, 0, 8, 0)
        left_lay.setSpacing(12)

        self._files_grp = QGroupBox("Generated Assets (same folder as PDF)")
        files_layout = QVBoxLayout(self._files_grp)
        self._files_lbl = QLabel("—")
        self._files_lbl.setWordWrap(True)
        files_layout.addWidget(self._files_lbl)
        left_lay.addWidget(self._files_grp)

        log_grp = QGroupBox("Build Activity Log")
        log_lay = QVBoxLayout(log_grp)
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setFont(QFont("Consolas", 9))
        self._log.setFixedHeight(180)
        log_lay.addWidget(self._log)
        left_lay.addWidget(log_grp)

        left_lay.addStretch()
        splitter.addWidget(left_pane)

        # Right Column: Viewport Grab Preview
        right_pane = QWidget()
        right_lay = QVBoxLayout(right_pane)
        right_lay.setContentsMargins(8, 0, 0, 0)
        right_lay.setSpacing(8)

        self._preview_grp = QGroupBox("3D Box Viewport Preview (Rendered by 3ds Max)")
        prev_lay = QVBoxLayout(self._preview_grp)
        self._preview_lbl = QLabel("3D viewport render will appear here after build.")
        self._preview_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview_lbl.setStyleSheet(
            "background: #18181c; color: #888; border: 1px dashed #444; border-radius: 4px; min-height: 250px;"
        )
        prev_lay.addWidget(self._preview_lbl)
        right_lay.addWidget(self._preview_grp)
        splitter.addWidget(right_pane)

        splitter.setSizes([450, 450])
        root.addWidget(splitter, stretch=1)

        # Buttons
        btn_row = QHBoxLayout()
        self._gen_btn = QPushButton("Save .ms File Only")
        self._send_btn = QPushButton("▶  Generate & Send to 3ds Max")
        self._open_btn = QPushButton("Open Output Folder")
        self._restart_btn = QPushButton("↩  Start Over")

        self._send_btn.setFixedHeight(42)
        self._send_btn.setStyleSheet(
            "font-weight: bold; font-size: 11pt; background: #1a7a2a; color: white; border-radius: 4px; padding: 0 16px;"
        )

        self._gen_btn.clicked.connect(self._save_only)
        self._send_btn.clicked.connect(self._send_to_max)
        self._open_btn.clicked.connect(self._open_folder)
        self._restart_btn.clicked.connect(self.step_done)

        btn_row.addWidget(self._gen_btn)
        btn_row.addWidget(self._send_btn)
        btn_row.addStretch()
        btn_row.addWidget(self._open_btn)
        btn_row.addWidget(self._restart_btn)
        root.addLayout(btn_row)

    def activate(self):
        s = self._session
        lines = []
        pdf_stem = os.path.splitext(os.path.basename(s.pdf_path))[0]
        max_stem_len = max(16, 210 - len(s.output_dir) - 5)
        safe_stem = pdf_stem[:max_stem_len]
        max_names = [f"{safe_stem}.max", "package_box.max", f"{pdf_stem}.max"]

        for name in ("diecutter_texture.png", "uv_overlay_check.png", "build_box_package.ms"):
            full = os.path.join(s.output_dir, name)
            exists = "✅" if os.path.isfile(full) else "⏳"
            lines.append(f"{exists}  {name}")

        has_max = any(os.path.isfile(os.path.join(s.output_dir, mn)) for mn in max_names)
        lines.append(f"{'✅' if has_max else '⏳'}  package_box.max")
        self._files_lbl.setText("\n".join(lines))
        self._update_viewport_preview()

    def _update_viewport_preview(self):
        grab_path = os.path.join(self._session.output_dir, "viewport_grab.jpg")
        if os.path.isfile(grab_path) and os.path.getsize(grab_path) > 1000:
            pix = QPixmap(grab_path)
            if not pix.isNull():
                scaled = pix.scaled(
                    450, 320,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )
                self._preview_lbl.setPixmap(scaled)
                self._preview_lbl.setStyleSheet("border: 1px solid #333; background: #000;")
                return
        self._preview_lbl.setText("3D viewport render will appear here after build.")
        self._preview_lbl.setStyleSheet(
            "background: #18181c; color: #888; border: 1px dashed #444; border-radius: 4px; min-height: 250px;"
        )

    def _log_line(self, text: str):
        self._log.append(f"> {text}")

    def _save_only(self):
        from core.maxscript_gen import generate_maxscript
        try:
            path = generate_maxscript(self._session)
            self._log_line(f"MaxScript saved: {path}")
            self.activate()
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))

    def _send_to_max(self):
        from core.maxscript_gen import generate_maxscript
        try:
            ms_path = generate_maxscript(self._session)
            self._log_line(f"MaxScript generated: {ms_path}")

            self._send_btn.setEnabled(False)
            self._gen_btn.setEnabled(False)

            self._build_thread = threading.Thread(
                target=self._run_max_build,
                args=(ms_path,),
                daemon=True,
            )
            self._build_thread.start()
        except Exception as exc:
            self._log_line(f"ERROR: {exc}")
            QMessageBox.critical(self, "Error", str(exc))
            self._send_btn.setEnabled(True)
            self._gen_btn.setEnabled(True)

    def _run_max_build(self, ms_path: str):
        from core.send_to_max import run_ms_file

        s = self._session
        pdf_dir = s.output_dir
        pdf_stem = os.path.splitext(os.path.basename(s.pdf_path))[0]
        max_stem_len = max(16, 210 - len(pdf_dir) - 5)
        safe_stem = pdf_stem[:max_stem_len]
        max_path = os.path.join(pdf_dir, f"{safe_stem}.max")
        status_path = os.path.join(pdf_dir, "build_status.txt")
        grab_path = os.path.join(pdf_dir, "viewport_grab.jpg")

        start_time = time.time()

        # Remove previous status and grab files so stale ones are never used
        for f in (status_path, grab_path):
            if os.path.exists(f):
                try:
                    os.remove(f)
                except Exception:
                    pass

        self._signals.log_msg.emit("Sending 'fileIn' command to 3ds Max...")
        ok = run_ms_file(ms_path)
        if not ok:
            self._signals.log_msg.emit("ERROR: 3ds Max window was not detected.")
            self._signals.log_msg.emit(f"Please ensure 3ds Max is running, or execute manually: {ms_path}")
            self._signals.build_finished.emit(False, "3ds Max window not found. Please ensure 3ds Max is running.")
            return

        self._signals.log_msg.emit("Building packaging carton in 3ds Max...")

        success = False
        error_msg = ""
        max_attempts = 50  # 50 * 0.5s = 25s

        for _ in range(max_attempts):
            time.sleep(0.5)
            if os.path.exists(status_path):
                mtime = os.path.getmtime(status_path)
                if mtime >= start_time - 1.0:
                    try:
                        with open(status_path, "r", encoding="utf-8", errors="replace") as f:
                            content = f.read().strip()
                        if content.startswith("SUCCESS"):
                            success = True
                            break
                        elif content.startswith("ERROR"):
                            error_msg = content
                            break
                    except Exception:
                        pass

        if success:
            size_kb = round(os.path.getsize(max_path) / 1024) if os.path.exists(max_path) else 0
            self._signals.log_msg.emit("SUCCESS: 3ds Max finished constructing the 3D carton box!")
            self._signals.log_msg.emit(f"Saved asset: {max_path} ({size_kb} KB)")
            self._signals.build_finished.emit(True, f"Box successfully built in 3ds Max!\nAsset: {max_path}")
        elif error_msg:
            self._signals.log_msg.emit(f"3ds Max execution error: {error_msg}")
            self._signals.build_finished.emit(False, f"3ds Max reported an error:\n{error_msg}")
        else:
            self._signals.log_msg.emit("Note: Timed out waiting for 3ds Max status.")
            self._signals.log_msg.emit(f"Script located at: {ms_path}")
            self._signals.build_finished.emit(False, "Timed out waiting for 3ds Max to report completion.")

    @pyqtSlot(bool, str)
    def _on_build_completed(self, success: bool, message: str):
        self._send_btn.setEnabled(True)
        self._gen_btn.setEnabled(True)
        self.activate()
        if success:
            QMessageBox.information(self, "Success", message)
        else:
            QMessageBox.warning(self, "Notice", message)

    def _open_folder(self):
        import subprocess
        folder = self._session.output_dir
        if os.path.isdir(folder):
            subprocess.Popen(f'explorer "{folder}"')
