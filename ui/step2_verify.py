"""
Step 2 – UV overlay verification viewer.
"""
import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QCheckBox, QGroupBox, QMessageBox, QFileDialog,
)
from PyQt6.QtCore import pyqtSignal

from ui.widgets.overlay_canvas import OverlayCanvas


class Step2Verify(QWidget):
    step_done = pyqtSignal()

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self._session = session
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        root.addWidget(QLabel("<h2>③ Verify UV Overlay</h2>"))
        root.addWidget(QLabel(
            "Inspect the overlay: <span style='color:cyan'>Cyan = cuts</span>, "
            "<span style='color:yellow'>Yellow = fold lines</span>. "
            "Confirm that fold lines fall in the gutters and no artwork crosses them."
        ))

        self._canvas = OverlayCanvas()
        root.addWidget(self._canvas, stretch=1)

        # Checklist
        grp = QGroupBox("Checklist")
        gv  = QVBoxLayout(grp)
        self._checks = [
            QCheckBox("Fold lines fall in gutters between language panels"),
            QCheckBox("No illustrations or text cross a fold line"),
            QCheckBox("Top lid artwork is above the top hinge"),
            QCheckBox("Bottom flap artwork is below the bottom hinge"),
        ]
        for cb in self._checks:
            gv.addWidget(cb)
        root.addWidget(grp)

        row = QHBoxLayout()
        save_btn = QPushButton("Save Overlay Image…")
        save_btn.clicked.connect(self._save_overlay)
        row.addWidget(save_btn)
        row.addStretch()
        self._confirm_btn = QPushButton("Looks Good  →")
        self._confirm_btn.setFixedHeight(34)
        self._confirm_btn.clicked.connect(self.step_done)
        row.addWidget(self._confirm_btn)
        root.addLayout(row)

    def activate(self):
        """Called when this step becomes visible. Render and show overlay."""
        from core.uv_overlay import render_uv_overlay
        try:
            path = render_uv_overlay(self._session)
            self._canvas.load_file(path)
        except Exception as exc:
            QMessageBox.critical(self, "Overlay error", str(exc))

    def _save_overlay(self):
        dst, _ = QFileDialog.getSaveFileName(
            self, "Save overlay", self._session.overlay_path,
            "PNG image (*.png)"
        )
        if dst and self._session.overlay_path:
            import shutil
            shutil.copyfile(self._session.overlay_path, dst)
