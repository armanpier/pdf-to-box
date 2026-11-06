"""
Step 1 – Texture alignment panel.
Left pane: rasterised PDF preview.
Right pane: diffuse texture with live PDF overlay, orthogonal un-warped drag handles,
and direct Transform Controls (Position / Rotation / Scale).
"""
import os
import cv2
import numpy as np

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QSplitter, QMessageBox, QFrame, QDoubleSpinBox,
    QCheckBox, QGroupBox
)
from PyQt6.QtCore import pyqtSignal, Qt, QThread, pyqtSlot

from ui.widgets.image_canvas import ImageCanvas
from ui.widgets.align_canvas import AlignCanvas
from core.manual_aligner import (
    update_session_from_handles,
    compute_transform_from_params,
    get_transform_params,
)


class _AlignWorker(QThread):
    """Background thread for auto-alignment (SIFT / AI / Crop)."""
    finished = pyqtSignal(dict)
    error    = pyqtSignal(str)

    def __init__(self, session, method: str):
        super().__init__()
        self._session = session
        self._method  = method

    def run(self):
        try:
            from core.texture_aligner import align_by_crop, align_by_sift, align_by_ai
            if self._method == "crop":
                t = align_by_crop(self._session)
            elif self._method == "ai":
                t = align_by_ai(self._session)
            else:
                t = align_by_sift(self._session)
            self.finished.emit(t)
        except Exception as exc:
            self.error.emit(str(exc))


class Step1Align(QWidget):
    step_done = pyqtSignal()

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self._session = session
        self._worker  = None
        self._block_spin_signals = False
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(6)

        title = QLabel("<h2>② Align Texture to PDF (AI + Rigid Sub-Pixel Registration)</h2>")
        root.addWidget(title)

        desc = QLabel(
            "Align the vector dieline to the diffuse texture. Use <b>SIFT</b>, "
            "<b>AI Match (Local VLM)</b>, or adjust <b>Position, Rotation, and Scale</b> below. "
            "Handles strictly preserve rectangle geometry (<b>Zero Warping / Zero Shearing</b>)."
        )
        desc.setWordWrap(True)
        root.addWidget(desc)

        # ── Splitter: PDF preview | Align canvas ────────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(4)

        # Left: PDF preview
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.addWidget(QLabel("<b>PDF Dieline</b>"))
        self._pdf_canvas = ImageCanvas()
        lv.addWidget(self._pdf_canvas)
        splitter.addWidget(left)

        # Right: align canvas
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.addWidget(QLabel("<b>Diffuse Texture (Live Dieline Overlay)</b>"))
        self._align_canvas = AlignCanvas()
        self._align_canvas.handles_changed.connect(self._on_handles_moved)
        rv.addWidget(self._align_canvas)
        splitter.addWidget(right)

        splitter.setSizes([380, 620])
        root.addWidget(splitter, stretch=1)

        # ── Transform Controls Panel (No Warping) ───────────────────────────
        t_box = QGroupBox("Rigid Alignment Controls (Position / Rotation / Scale - No Warping)")
        t_box.setStyleSheet("QGroupBox { font-weight: bold; }")
        t_layout = QVBoxLayout(t_box)
        t_layout.setContentsMargins(8, 8, 8, 8)
        t_layout.setSpacing(6)

        # Row 1: Position + Nudge
        r1 = QHBoxLayout()
        r1.addWidget(QLabel("Position Center X:"))
        self._pos_x_spin = QDoubleSpinBox()
        self._pos_x_spin.setRange(-20000.0, 30000.0)
        self._pos_x_spin.setSingleStep(5.0)
        self._pos_x_spin.setDecimals(1)
        self._pos_x_spin.setFixedWidth(90)
        self._pos_x_spin.valueChanged.connect(self._on_params_changed)
        r1.addWidget(self._pos_x_spin)

        r1.addWidget(QLabel("Y:"))
        self._pos_y_spin = QDoubleSpinBox()
        self._pos_y_spin.setRange(-20000.0, 30000.0)
        self._pos_y_spin.setSingleStep(5.0)
        self._pos_y_spin.setDecimals(1)
        self._pos_y_spin.setFixedWidth(90)
        self._pos_y_spin.valueChanged.connect(self._on_params_changed)
        r1.addWidget(self._pos_y_spin)

        # Nudge buttons
        r1.addSpacing(10)
        btn_left = QPushButton("←")
        btn_right = QPushButton("→")
        btn_up = QPushButton("↑")
        btn_down = QPushButton("↓")
        for b in (btn_left, btn_right, btn_up, btn_down):
            b.setFixedSize(28, 26)
            r1.addWidget(b)
        btn_left.clicked.connect(lambda: self._nudge(-10, 0))
        btn_right.clicked.connect(lambda: self._nudge(10, 0))
        btn_up.clicked.connect(lambda: self._nudge(0, -10))
        btn_down.clicked.connect(lambda: self._nudge(0, 10))

        r1.addSpacing(20)

        # Rotation
        r1.addWidget(QLabel("Rotation (°):"))
        self._rot_spin = QDoubleSpinBox()
        self._rot_spin.setRange(-360.0, 360.0)
        self._rot_spin.setSingleStep(1.0)
        self._rot_spin.setDecimals(1)
        self._rot_spin.setFixedWidth(80)
        self._rot_spin.valueChanged.connect(self._on_params_changed)
        r1.addWidget(self._rot_spin)

        rot_0_btn   = QPushButton("0°")
        rot_90_btn  = QPushButton("90°")
        rot_180_btn = QPushButton("180°")
        rot_270_btn = QPushButton("270°")
        for rb in (rot_0_btn, rot_90_btn, rot_180_btn, rot_270_btn):
            rb.setFixedSize(44, 26)
            r1.addWidget(rb)
        rot_0_btn.clicked.connect(lambda: self._set_rotation(0.0))
        rot_90_btn.clicked.connect(lambda: self._set_rotation(90.0))
        rot_180_btn.clicked.connect(lambda: self._set_rotation(180.0))
        rot_270_btn.clicked.connect(lambda: self._set_rotation(270.0))

        r1.addStretch()
        t_layout.addLayout(r1)

        # Row 2: Scale + Aspect Lock
        r2 = QHBoxLayout()
        r2.addWidget(QLabel("Scale X (px/pt):"))
        self._scale_x_spin = QDoubleSpinBox()
        self._scale_x_spin.setRange(0.01, 100.0)
        self._scale_x_spin.setSingleStep(0.05)
        self._scale_x_spin.setDecimals(4)
        self._scale_x_spin.setFixedWidth(95)
        self._scale_x_spin.valueChanged.connect(self._on_scale_x_changed)
        r2.addWidget(self._scale_x_spin)

        r2.addWidget(QLabel("Scale Y:"))
        self._scale_y_spin = QDoubleSpinBox()
        self._scale_y_spin.setRange(0.01, 100.0)
        self._scale_y_spin.setSingleStep(0.05)
        self._scale_y_spin.setDecimals(4)
        self._scale_y_spin.setFixedWidth(95)
        self._scale_y_spin.valueChanged.connect(self._on_scale_y_changed)
        r2.addWidget(self._scale_y_spin)

        self._lock_aspect_chk = QCheckBox("Lock Aspect Ratio (Uniform Scale)")
        self._lock_aspect_chk.setChecked(True)
        r2.addWidget(self._lock_aspect_chk)

        r2.addStretch()
        t_layout.addLayout(r2)

        root.addWidget(t_box)

        # ── Method Buttons & Quality ─────────────────────────────────────────
        ctrl = QHBoxLayout()

        self._sift_btn   = QPushButton("⚡ SIFT Match")
        self._ai_btn     = QPushButton("🤖 AI Match (Local VLM)")
        self._crop_btn   = QPushButton("🔍 White Crop")
        self._manual_btn = QPushButton("🎯 Drag Handles")
        self._manual_btn.setCheckable(True)

        for btn in (self._sift_btn, self._ai_btn, self._crop_btn, self._manual_btn):
            btn.setFixedHeight(34)
            ctrl.addWidget(btn)

        self._sift_btn.clicked.connect(lambda: self._run_auto("sift"))
        self._ai_btn.clicked.connect(lambda: self._run_auto("ai"))
        self._crop_btn.clicked.connect(lambda: self._run_auto("crop"))
        self._manual_btn.toggled.connect(self._toggle_manual)

        ctrl.addSpacing(20)

        ctrl.addWidget(QLabel("Confidence:"))
        self._quality_bar = QProgressBar()
        self._quality_bar.setRange(0, 100)
        self._quality_bar.setValue(0)
        self._quality_bar.setFixedWidth(140)
        self._quality_bar.setFixedHeight(18)
        ctrl.addWidget(self._quality_bar)

        self._quality_lbl = QLabel("—")
        ctrl.addWidget(self._quality_lbl)

        ctrl.addStretch()

        self._confirm_btn = QPushButton("Confirm Alignment  →")
        self._confirm_btn.setFixedHeight(34)
        self._confirm_btn.setEnabled(False)
        self._confirm_btn.setStyleSheet("font-weight: bold; background: #007ACC; color: white;")
        self._confirm_btn.clicked.connect(self._confirm)
        ctrl.addWidget(self._confirm_btn)

        root.addLayout(ctrl)

    # ── Public ────────────────────────────────────────────────────────────────

    def activate(self):
        """Called when this step becomes visible. Load images and run alignment."""
        s = self._session
        # Load PDF preview
        pdf_img = _render_pdf(s, dpi=100)
        self._pdf_canvas.load_image(pdf_img)
        # Load texture as align canvas background
        tex = cv2.imread(s.texture_path)
        if tex is not None:
            self._align_canvas.load_texture(tex)
        # Auto-run feature alignment (SIFT with AI fallback) immediately
        self._run_auto("sift")

    # ── Private Slots & Actions ───────────────────────────────────────────────

    def _run_auto(self, method: str):
        if self._worker and self._worker.isRunning():
            return
        self._set_busy(True)
        self._worker = _AlignWorker(self._session, method)
        self._worker.finished.connect(self._on_align_done)
        self._worker.error.connect(self._on_align_error)
        self._worker.start()

    @pyqtSlot(dict)
    def _on_align_done(self, transform: dict):
        self._set_busy(False)
        self._sync_spinboxes_from_transform(transform)
        self._update_quality(transform)
        self._update_overlay()

        s = self._session
        self._align_canvas.reset_handles_to_transform(transform, session=s)
        if self._manual_btn.isChecked():
            self._align_canvas.enable_handles()
        else:
            self._align_canvas.disable_handles()

        self._confirm_btn.setEnabled(True)

    @pyqtSlot(str)
    def _on_align_error(self, msg: str):
        self._set_busy(False)
        QMessageBox.warning(self, "Alignment failed", msg)

    def _toggle_manual(self, checked: bool):
        if checked:
            self._align_canvas.enable_handles()
        else:
            self._align_canvas.disable_handles()

    def _on_handles_moved(self, positions: list):
        """Live-update transform from handle positions (guaranteed non-warping)."""
        if not self._manual_btn.isChecked() or len(positions) != 4:
            return

        try:
            transform, rectified = update_session_from_handles(self._session, positions)
            # Snap canvas handles to rectified orthogonal rectangle
            self._align_canvas.set_handle_positions(rectified)
            self._sync_spinboxes_from_transform(transform)
            self._update_overlay()
            self._update_quality(transform)
        except Exception as exc:
            print(f"[Manual Align Warning] {exc}")

    def _sync_spinboxes_from_transform(self, transform: dict):
        """Update spinbox numbers to reflect current transform without re-triggering."""
        params = get_transform_params(transform, self._session)
        self._block_spin_signals = True
        try:
            self._pos_x_spin.setValue(params["pos_x"])
            self._pos_y_spin.setValue(params["pos_y"])
            self._rot_spin.setValue(params["rot_deg"])
            self._scale_x_spin.setValue(abs(params["scale_x"]))
            self._scale_y_spin.setValue(abs(params["scale_y"]))
        finally:
            self._block_spin_signals = False

    def _on_params_changed(self):
        """Called when position or rotation spinboxes change."""
        if self._block_spin_signals:
            return
        self._apply_spinbox_transform()

    def _on_scale_x_changed(self, val: float):
        if self._block_spin_signals:
            return
        if self._lock_aspect_chk.isChecked():
            self._block_spin_signals = True
            try:
                self._scale_y_spin.setValue(val)
            finally:
                self._block_spin_signals = False
        self._apply_spinbox_transform()

    def _on_scale_y_changed(self, val: float):
        if self._block_spin_signals:
            return
        if self._lock_aspect_chk.isChecked():
            self._block_spin_signals = True
            try:
                self._scale_x_spin.setValue(val)
            finally:
                self._block_spin_signals = False
        self._apply_spinbox_transform()

    def _nudge(self, dx: float, dy: float):
        self._pos_x_spin.setValue(self._pos_x_spin.value() + dx)
        self._pos_y_spin.setValue(self._pos_y_spin.value() + dy)

    def _set_rotation(self, deg: float):
        self._rot_spin.setValue(deg)

    def _apply_spinbox_transform(self):
        px = self._pos_x_spin.value()
        py = self._pos_y_spin.value()
        rot = self._rot_spin.value()
        sx = self._scale_x_spin.value()
        sy = self._scale_y_spin.value()

        transform, rectified = compute_transform_from_params(
            pos_x=px, pos_y=py, rot_deg=rot,
            scale_x=sx, scale_y=sy,
            session=self._session
        )
        self._session.transform = transform
        self._session.align_method = "manual"
        self._session.align_quality = 1.0

        self._align_canvas.set_handle_positions(rectified)
        self._update_overlay()
        self._update_quality(transform)
        self._confirm_btn.setEnabled(True)

    def _update_overlay(self):
        """Re-render the warped PDF overlay on the align canvas."""
        s = self._session
        t = s.transform
        if not t or s.pdf_doc is None:
            return

        try:
            pdf_img = _render_pdf(s, dpi=72)
            M = t.get("M_affine")
            H_tex = max(1, t.get("H_tex", 1))
            W_tex = max(1, t.get("W_tex", 1))

            if M is not None:
                warped = cv2.warpAffine(
                    pdf_img, np.float32(M), (W_tex, H_tex),
                    flags=cv2.INTER_LINEAR,
                    borderMode=cv2.BORDER_CONSTANT,
                    borderValue=(255, 255, 255),
                )
            else:
                sx, sy = t.get("scale_x", 1.0), t.get("scale_y", 1.0)
                ox, oy = t.get("offset_x", 0.0), t.get("offset_y", 0.0)
                M_mat = np.float32([[sx, 0, ox], [0, sy, oy]])
                warped = cv2.warpAffine(
                    pdf_img, M_mat, (W_tex, H_tex),
                    flags=cv2.INTER_LINEAR,
                    borderMode=cv2.BORDER_CONSTANT,
                    borderValue=(255, 255, 255),
                )
            self._align_canvas.set_pdf_overlay(warped, alpha=0.45)
        except Exception as exc:
            print(f"[Overlay Update Warning] {exc}")

    def _update_quality(self, transform: dict):
        quality = int(self._session.align_quality * 100)
        inliers = transform.get("inliers", 0)
        method  = self._session.align_method
        rot     = transform.get("rot_deg", 0.0)
        self._quality_bar.setValue(quality)
        self._quality_lbl.setText(f"{quality}%  ({method}, {inliers} inliers, {rot:.1f}°)")

    def _set_busy(self, busy: bool):
        for btn in (self._sift_btn, self._ai_btn, self._crop_btn, self._manual_btn, self._confirm_btn):
            btn.setEnabled(not busy)
        if busy:
            self._quality_lbl.setText("Analyzing…")

    def _confirm(self):
        self.step_done.emit()


def _render_pdf(session, dpi: int = 72) -> np.ndarray:
    if session.pdf_doc is None:
        return np.full((100, 100, 3), 255, dtype=np.uint8)
    page = session.pdf_doc[0]
    pix  = page.get_pixmap(dpi=dpi)
    return cv2.imdecode(np.frombuffer(pix.tobytes(), np.uint8), cv2.IMREAD_COLOR)
