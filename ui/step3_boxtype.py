"""
Step 3 – Visual Face Mapping & 3D Box Setup.
Auto-detects the 4 body panels, identifies the box dimensions,
and lets the user pick which panel is the Front (Hero) face
with live visual color feedback. Zero packaging jargon required.
"""
import os
import cv2
import numpy as np

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QRadioButton,
    QButtonGroup, QGroupBox, QDoubleSpinBox, QFormLayout,
    QPushButton, QSplitter, QGraphicsRectItem, QGraphicsSimpleTextItem,
    QGraphicsItem, QGraphicsScene, QGraphicsView, QMessageBox,
    QCheckBox, QComboBox, QFrame,
)
from PyQt6.QtCore import pyqtSignal, Qt, QRectF, QPointF
from PyQt6.QtGui import QPen, QBrush, QColor, QFont, QMouseEvent, QCursor, QPixmap

from ui.widgets.image_canvas import ImageCanvas, numpy_to_qpixmap
from core.panel_parser import parse_panels, _compute_panel_uvs


FACE_COLORS = {
    "front":  QColor(0, 160, 255),    # Vibrant Blue
    "back":   QColor(40, 200, 80),    # Vibrant Green
    "left":   QColor(255, 140, 30),   # Vibrant Orange
    "right":  QColor(255, 215, 0),    # Golden Yellow
    "top":    QColor(190, 60, 230),   # Purple
    "bottom": QColor(160, 90, 120),   # Plum
}

FACE_NAMES = {
    "front":  "FRONT (Hero)",
    "back":   "BACK FACE",
    "left":   "LEFT SIDE",
    "right":  "RIGHT SIDE",
    "top":    "TOP LID",
    "bottom": "BOTTOM LID",
}


class _PanelOverlayRect(QGraphicsRectItem):
    """Interactive rectangle representing a panel face in the graphics scene."""

    def __init__(self, rect: QRectF, face_name: str, panel_idx: int | None,
                 label: str | None = None, is_ignored: bool = False, is_dust_flap: bool = False, parent=None):
        super().__init__(rect, parent)
        self.face_name = face_name
        self.panel_idx = panel_idx
        self.is_ignored = is_ignored
        self.is_dust_flap = is_dust_flap
        self.setData(0, panel_idx)

        if is_ignored:
            self._color = QColor(160, 160, 165)
            pen = QPen(self._color, 3, Qt.PenStyle.DashLine)
            fill_color = QColor(110, 110, 115, 60)
        elif is_dust_flap:
            self._color = QColor(110, 180, 220)
            pen = QPen(self._color, 2, Qt.PenStyle.DashDotLine)
            fill_color = QColor(60, 140, 190, 45)
        else:
            self._color = FACE_COLORS.get(face_name, QColor(200, 200, 200))
            pen = QPen(self._color, 4, Qt.PenStyle.SolidLine)
            fill_color = QColor(self._color.red(), self._color.green(), self._color.blue(), 75)

        pen.setCosmetic(True)
        self.setPen(pen)
        self.setBrush(QBrush(fill_color))
        self.setZValue(10)

        if is_ignored:
            self.setToolTip("Excluded from 3D box body (included in flat 2D package)")
        elif is_dust_flap:
            self.setToolTip("Flap geometry (included in flat 2D package)")
        elif panel_idx is not None:
            self.setAcceptHoverEvents(True)
            self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            self.setToolTip(f"Click to set Panel {panel_idx + 1} as Front face")

        # Constant screen-size label badge
        label_text = label if label else FACE_NAMES.get(face_name, face_name.upper())

        self._badge_bg = QGraphicsRectItem(self)
        self._badge_bg.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        self._badge_bg.setBrush(QBrush(QColor(18, 18, 22, 230)))
        badge_pen = QPen(self._color, 2.0)
        badge_pen.setCosmetic(True)
        self._badge_bg.setPen(badge_pen)
        self._badge_bg.setZValue(20)

        font_size = 9 if is_dust_flap else 11
        self._badge_txt = QGraphicsSimpleTextItem(label_text, self._badge_bg)
        self._badge_txt.setFont(QFont("Segoe UI", font_size, QFont.Weight.Bold))
        self._badge_txt.setBrush(QBrush(QColor("white")))
        self._badge_txt.setZValue(21)

        br = self._badge_txt.boundingRect()
        pad_x, pad_y = (8.0, 4.0) if is_dust_flap else (12.0, 6.0)
        bw = br.width() + pad_x * 2
        bh = br.height() + pad_y * 2
        self._badge_bg.setRect(-bw / 2.0, -bh / 2.0, bw, bh)
        self._badge_txt.setPos(-bw / 2.0 + pad_x, -bh / 2.0 + pad_y)

        # Center badge inside the panel rectangle in scene coordinates
        self._badge_bg.setPos(rect.center())

    def hoverEnterEvent(self, event):
        if self.panel_idx is not None:
            pen = QPen(self._color, 6, Qt.PenStyle.SolidLine)
            pen.setCosmetic(True)
            self.setPen(pen)
            self.setBrush(QBrush(QColor(self._color.red(), self._color.green(), self._color.blue(), 130)))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        if self.panel_idx is not None:
            pen = QPen(self._color, 4, Qt.PenStyle.SolidLine)
            pen.setCosmetic(True)
            self.setPen(pen)
            self.setBrush(QBrush(QColor(self._color.red(), self._color.green(), self._color.blue(), 75)))
        super().hoverLeaveEvent(event)


class _InteractivePanelCanvas(ImageCanvas):
    """Canvas that displays texture with native interactive panel overlay rectangles."""

    panel_clicked = pyqtSignal(int)  # Emits panel index 0..3

    def __init__(self, parent=None):
        super().__init__(parent)
        self._panel_items: list[_PanelOverlayRect] = []

    def clear_panels(self):
        for item in self._panel_items:
            self._scene.removeItem(item)
        self._panel_items.clear()

    def add_panel(self, rect: QRectF, face_name: str, panel_idx: int | None,
                  label: str | None = None, is_ignored: bool = False, is_dust_flap: bool = False):
        item = _PanelOverlayRect(rect, face_name, panel_idx, label, is_ignored=is_ignored, is_dust_flap=is_dust_flap)
        self._scene.addItem(item)
        self._panel_items.append(item)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            item = self.itemAt(event.position().toPoint())
            while item:
                if isinstance(item, _PanelOverlayRect) and item.panel_idx is not None:
                    self.panel_clicked.emit(item.panel_idx)
                    return
                item = item.parentItem()
        super().mousePressEvent(event)


class Step3BoxType(QWidget):
    step_done = pyqtSignal()

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self._session = session
        self._updating = False
        self._texture_loaded = False
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        # ── Header ───────────────────────────────────────────────────────────
        title = QLabel("<h2>④ Map Faces to 3D Box</h2>")
        root.addWidget(title)

        desc = QLabel(
            "The 4 carton panels were detected automatically. "
            "Select which panel is your <b>Front (Hero) face</b> (click directly on the preview image or choose below). "
            "All other faces and dimensions are updated automatically."
        )
        desc.setWordWrap(True)
        root.addWidget(desc)

        # ── Splitter: Canvas on left, Controls on right ──────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(4)

        # Left pane: Interactive panel map preview
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel("<b>Dieline Face Map</b> (Click any panel to set it as Front)"))

        self._canvas = _InteractivePanelCanvas()
        self._canvas.panel_clicked.connect(self._on_canvas_panel_clicked)
        left_layout.addWidget(self._canvas)
        splitter.addWidget(left_widget)

        # Right pane: Controls & summaries
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(8, 0, 8, 0)
        right_layout.setSpacing(12)

        # Carton type badge
        self._type_badge = QLabel("Auto-detected: <b>Standard Folding Carton</b>")
        self._type_badge.setStyleSheet(
            "background: #2a3b4c; color: #64b5f6; padding: 6px 10px; border-radius: 4px; font-size: 10.5pt;"
        )
        self._type_badge.setWordWrap(True)
        right_layout.addWidget(self._type_badge)

        # Multi-Column Warning & Flap Management Banner (Shown when >4 columns)
        self._multi_col_frame = QFrame()
        self._multi_col_frame.setStyleSheet("""
            QFrame {
                background: #2b2513;
                border: 1px solid #ffd54f;
                border-radius: 6px;
                padding: 6px;
            }
        """)
        m_lay = QVBoxLayout(self._multi_col_frame)
        m_lay.setContentsMargins(8, 8, 8, 8)
        m_lay.setSpacing(6)

        m_title = QLabel("⚠️ <b>Multi-Column Net Detected (5+ Columns)</b>")
        m_title.setStyleSheet("color: #ffd54f; font-size: 10.5pt;")
        m_lay.addWidget(m_title)

        m_desc = QLabel(
            "A 3D box folds from 4 walls. Select which outer panel is the extra glue/sleeve tab to exclude from the 3D folded body (all panels & flaps are kept in the flat net):"
        )
        m_desc.setStyleSheet("color: #e0e0e0; font-size: 9pt;")
        m_desc.setWordWrap(True)
        m_lay.addWidget(m_desc)

        self._col_ignore_grp = QButtonGroup(self)
        self._ignore_left_rb = QRadioButton("Exclude Panel 1 (Far Left) → Use Panels 2, 3, 4, 5 [AI Recommended 🤖]")
        self._ignore_left_rb.setStyleSheet("color: #81c784; font-weight: bold;")
        self._ignore_right_rb = QRadioButton("Exclude Far Right Panel → Use Left Panels")
        self._ignore_right_rb.setStyleSheet("color: #ffb74d;")
        self._col_ignore_grp.addButton(self._ignore_left_rb, 0)
        self._col_ignore_grp.addButton(self._ignore_right_rb, 1)
        m_lay.addWidget(self._ignore_left_rb)
        m_lay.addWidget(self._ignore_right_rb)
        self._col_ignore_grp.idToggled.connect(self._on_ignore_col_toggled)

        ai_btn = QPushButton("🤖 Ask Bionic / AI to Auto-Decide")
        ai_btn.setFixedHeight(28)
        ai_btn.setStyleSheet("background: #1e3320; border: 1px solid #4caf50; color: #a5d6a7; font-weight: bold;")
        ai_btn.clicked.connect(self._on_ask_ai_multi_column)
        m_lay.addWidget(ai_btn)

        self._multi_col_frame.setVisible(False)
        right_layout.addWidget(self._multi_col_frame)

        # Front Face Selector Group
        front_grp = QGroupBox("Select Front (Hero) Face")
        self._front_layout = QVBoxLayout(front_grp)
        self._btn_group = QButtonGroup(self)
        self._radio_buttons = []

        for i in range(4):
            rb = QRadioButton(f"Panel {i+1}")
            rb.setProperty("panel_idx", i)
            self._btn_group.addButton(rb)
            self._front_layout.addWidget(rb)
            self._radio_buttons.append(rb)

        self._btn_group.buttonToggled.connect(self._on_front_radio_toggled)

        # Quick action buttons
        btn_row = QHBoxLayout()
        self._swap_btn = QPushButton("🔄 Swap Front ↔ Back")
        self._swap_btn.clicked.connect(self._swap_front_back)
        btn_row.addWidget(self._swap_btn)

        self._reset_btn = QPushButton("↺ Auto-Pick Default")
        self._reset_btn.clicked.connect(self._reset_default)
        btn_row.addWidget(self._reset_btn)
        self._front_layout.addLayout(btn_row)

        right_layout.addWidget(front_grp)

        # Settings & Orientation Group
        settings_grp = QGroupBox("⚙️ Orientation & Flap Settings")
        set_lay = QVBoxLayout(settings_grp)
        set_lay.setSpacing(8)

        self._upside_down_chk = QCheckBox("Box / Texture is upside down (Flip 180°)")
        self._upside_down_chk.setStyleSheet("font-weight: bold; color: #ffca28;")
        self._upside_down_chk.setToolTip("Check if flat dieline artwork is upside down; inverts 3D face UVs and swaps top/bottom lids.")
        self._upside_down_chk.toggled.connect(self._on_upside_down_toggled)
        set_lay.addWidget(self._upside_down_chk)

        flap_form = QFormLayout()
        flap_form.setContentsMargins(0, 4, 0, 0)
        flap_form.setSpacing(6)

        # Top lid row
        top_row = QHBoxLayout()
        self._top_lid_combo = QComboBox()
        self._top_lid_combo.addItems(["Auto-Detect", "Panel 1", "Panel 2", "Panel 3", "Panel 4"])
        self._top_lid_combo.currentIndexChanged.connect(self._on_top_lid_changed)
        top_row.addWidget(self._top_lid_combo, stretch=1)

        self._flip_top_chk = QCheckBox("Flip 180°")
        self._flip_top_chk.setToolTip("Rotate Top Lid UV 180 degrees")
        self._flip_top_chk.toggled.connect(self._on_flip_top_toggled)
        top_row.addWidget(self._flip_top_chk)
        flap_form.addRow("Top Lid:", top_row)

        # Bottom lid row
        bot_row = QHBoxLayout()
        self._bot_lid_combo = QComboBox()
        self._bot_lid_combo.addItems(["Auto-Detect", "Panel 1", "Panel 2", "Panel 3", "Panel 4"])
        self._bot_lid_combo.currentIndexChanged.connect(self._on_bot_lid_changed)
        bot_row.addWidget(self._bot_lid_combo, stretch=1)

        self._flip_bot_chk = QCheckBox("Flip 180°")
        self._flip_bot_chk.setToolTip("Rotate Bottom Lid UV 180 degrees")
        self._flip_bot_chk.toggled.connect(self._on_flip_bot_toggled)
        bot_row.addWidget(self._flip_bot_chk)
        flap_form.addRow("Bottom Lid:", bot_row)

        set_lay.addLayout(flap_form)
        right_layout.addWidget(settings_grp)

        # Dimensions Group
        dim_grp = QGroupBox("3D Box Dimensions (mm)")
        dim_form = QFormLayout(dim_grp)

        self._w_spin = QDoubleSpinBox()
        self._w_spin.setRange(1.0, 9999.0)
        self._w_spin.setDecimals(1)
        self._w_spin.setSuffix(" mm")
        self._w_spin.valueChanged.connect(self._on_dim_changed)

        self._d_spin = QDoubleSpinBox()
        self._d_spin.setRange(1.0, 9999.0)
        self._d_spin.setDecimals(1)
        self._d_spin.setSuffix(" mm")
        self._d_spin.valueChanged.connect(self._on_dim_changed)

        self._h_spin = QDoubleSpinBox()
        self._h_spin.setRange(1.0, 9999.0)
        self._h_spin.setDecimals(1)
        self._h_spin.setSuffix(" mm")
        self._h_spin.valueChanged.connect(self._on_dim_changed)

        dim_form.addRow("Width  (W):", self._w_spin)
        dim_form.addRow("Depth  (D):", self._d_spin)
        dim_form.addRow("Height (H):", self._h_spin)
        right_layout.addWidget(dim_grp)

        # Mapping Summary Label
        summary_grp = QGroupBox("3D Face Assignments")
        sum_lay = QVBoxLayout(summary_grp)
        self._summary_lbl = QLabel("—")
        self._summary_lbl.setTextFormat(Qt.TextFormat.RichText)
        self._summary_lbl.setWordWrap(True)
        sum_lay.addWidget(self._summary_lbl)
        right_layout.addWidget(summary_grp)

        right_layout.addStretch()

        # Navigation
        nav_row = QHBoxLayout()
        nav_row.addStretch()
        self._next_btn = QPushButton("Proceed to Build  →")
        self._next_btn.setFixedHeight(38)
        self._next_btn.setStyleSheet("font-weight: bold; background: #007acc; color: white; padding: 0 18px;")
        self._next_btn.clicked.connect(self._confirm)
        nav_row.addWidget(self._next_btn)
        right_layout.addLayout(nav_row)

        splitter.addWidget(right_widget)
        splitter.setSizes([550, 450])
        root.addWidget(splitter, stretch=1)

    # ── Public Lifecycle ──────────────────────────────────────────────────────

    def activate(self):
        """Called as soon as Step 3 becomes visible. Auto-parses panels and populates UI."""
        self._updating = True
        try:
            # 1. Load background texture into canvas once
            if not self._texture_loaded or self._canvas._pixmap_item is None:
                diffuse = cv2.imread(self._session.texture_path)
                if diffuse is not None:
                    self._canvas.load_image(diffuse)
                    self._texture_loaded = True

            # 2. Parse panels with auto-detected front
            parse_panels(self._session, front_idx=self._session.front_panel_idx)
            self._sync_ui_from_session()
        finally:
            self._updating = False

    # ── Internal Actions ──────────────────────────────────────────────────────

    def _sync_ui_from_session(self):
        """Refresh radio labels, dimensions, face summary, and visual overlay rects."""
        s = self._session
        body = s.detected_body_panels
        cols = getattr(s, "all_columns_info", [])
        f_idx = s.front_panel_idx if s.front_panel_idx is not None else 0

        # 1. Update carton badge
        self._type_badge.setText(f"📦 Identified Carton: <b>{s.box_type_name}</b>")

        # 2. Multi-column warning & flap selection
        if len(cols) > 4:
            self._multi_col_frame.setVisible(True)
            self._ignore_left_rb.blockSignals(True)
            self._ignore_right_rb.blockSignals(True)
            self._ignore_left_rb.setText(
                f"Exclude Panel 1 ({cols[0]['w_mm']:.1f} mm, Far Left) → Use Panels 2..{len(cols)} [AI Recommended 🤖]"
            )
            self._ignore_right_rb.setText(
                f"Exclude Panel {len(cols)} ({cols[-1]['w_mm']:.1f} mm, Far Right) → Use Panels 1..{len(cols)-1}"
            )
            if s.ignored_col_idx == 0:
                self._ignore_left_rb.setChecked(True)
            else:
                self._ignore_right_rb.setChecked(True)
            self._ignore_left_rb.blockSignals(False)
            self._ignore_right_rb.blockSignals(False)
        else:
            self._multi_col_frame.setVisible(False)

        # 3. Identify the single panel with the primary main lid
        top_flaps = [p.get("top_flap_h_mm", 0) for p in body]
        main_lid_idx = int(np.argmax(top_flaps)) if top_flaps and max(top_flaps) > 10 else -1

        # 4. Update radio button labels with actual panel numbers
        for i, rb in enumerate(self._radio_buttons):
            if i < len(body):
                p = body[i]
                actual_num = p.get("panel_number", i + 1)
                w = p.get("w_mm", 0)
                h = p.get("h_mm", 0)
                tag = ""
                if i == main_lid_idx:
                    tag = " ⭐ (Has Main Lid)"
                elif i == (f_idx + 2) % 4:
                    tag = " (Opposite Face)"
                else:
                    tag = " (Side Face)"

                rb.setText(f"Panel {actual_num} [{w:.1f} × {h:.1f} mm]{tag}")
                rb.setEnabled(True)
                rb.setVisible(True)
                if i == f_idx:
                    rb.setChecked(True)
            else:
                rb.setEnabled(False)
                rb.setVisible(False)

        # 5. Update dimensions spinboxes
        dims = s.box_dims_mm
        self._w_spin.setValue(dims.get("W", 64.0))
        self._d_spin.setValue(dims.get("D", 73.0))
        self._h_spin.setValue(dims.get("H", 118.0))

        # 6. Update Orientation & Flap Settings controls
        self._upside_down_chk.blockSignals(True)
        self._upside_down_chk.setChecked(bool(s.is_upside_down))
        self._upside_down_chk.blockSignals(False)

        top_p = s.top_lid_panel_idx + 1 if s.top_lid_panel_idx is not None else 1
        bot_p = s.bot_lid_panel_idx + 1 if s.bot_lid_panel_idx is not None else 1

        top_attached_num = body[top_p - 1]["panel_number"] if top_p - 1 < len(body) else top_p
        bot_attached_num = body[bot_p - 1]["panel_number"] if bot_p - 1 < len(body) else bot_p

        self._top_lid_combo.blockSignals(True)
        self._top_lid_combo.setItemText(0, f"Auto-Detect (Panel {top_attached_num})")
        self._top_lid_combo.setCurrentIndex(0 if s.top_lid_panel_idx is None else (s.top_lid_panel_idx + 1))
        self._top_lid_combo.blockSignals(False)

        self._bot_lid_combo.blockSignals(True)
        self._bot_lid_combo.setItemText(0, f"Auto-Detect (Panel {bot_attached_num})")
        self._bot_lid_combo.setCurrentIndex(0 if s.bot_lid_panel_idx is None else (s.bot_lid_panel_idx + 1))
        self._bot_lid_combo.blockSignals(False)

        self._flip_top_chk.blockSignals(True)
        self._flip_top_chk.setChecked(bool(s.flip_top_lid_180))
        self._flip_top_chk.blockSignals(False)

        self._flip_bot_chk.blockSignals(True)
        self._flip_bot_chk.setChecked(bool(s.flip_bot_lid_180))
        self._flip_bot_chk.blockSignals(False)

        # 7. Update Summary HTML
        f_panel_num = body[f_idx]["panel_number"] if f_idx < len(body) else (f_idx + 1)
        if s.is_upside_down:
            L_num = body[(f_idx + 1) % 4]["panel_number"] if (f_idx + 1) % 4 < len(body) else 2
            B_num = body[(f_idx + 2) % 4]["panel_number"] if (f_idx + 2) % 4 < len(body) else 3
            R_num = body[(f_idx + 3) % 4]["panel_number"] if (f_idx + 3) % 4 < len(body) else 4
            orient_note = '<tr><td colspan="2"><span style="color:#ffca28; font-weight:bold;">⚠️ Box / Texture is UPSIDE DOWN (180° Inverted)</span></td></tr>'
        else:
            R_num = body[(f_idx + 1) % 4]["panel_number"] if (f_idx + 1) % 4 < len(body) else 2
            B_num = body[(f_idx + 2) % 4]["panel_number"] if (f_idx + 2) % 4 < len(body) else 3
            L_num = body[(f_idx + 3) % 4]["panel_number"] if (f_idx + 3) % 4 < len(body) else 4
            orient_note = '<tr><td colspan="2"><span style="color:#64b5f6;">Orientation: Standard (Right-side up)</span></td></tr>'

        summary_html = f"""
        <table style="line-height: 1.6; font-size: 10pt;">
          {orient_note}
          <tr><td><span style="color:#00a0ff; font-weight:bold;">🟦 Front Face:</span></td><td>Panel {f_panel_num} ({dims.get('W')} mm)</td></tr>
          <tr><td><span style="color:#28c850; font-weight:bold;">🟩 Back Face:</span></td><td>Panel {B_num} ({dims.get('W')} mm)</td></tr>
          <tr><td><span style="color:#ff8c1e; font-weight:bold;">🟧 Left Face:</span></td><td>Panel {L_num} ({dims.get('D')} mm)</td></tr>
          <tr><td><span style="color:#ffd700; font-weight:bold;">🟨 Right Face:</span></td><td>Panel {R_num} ({dims.get('D')} mm)</td></tr>
          <tr><td><span style="color:#be3ce6; font-weight:bold;">🟪 Top Lid:</span></td><td>Attached to Panel {top_attached_num} {'(180° Flipped)' if s.flip_top_lid_180 else ''}</td></tr>
          <tr><td><span style="color:#a05a78; font-weight:bold;">🟫 Bottom Lid:</span></td><td>Attached to Panel {bot_attached_num} {'(180° Flipped)' if s.flip_bot_lid_180 else ''}</td></tr>
        </table>
        """
        self._summary_lbl.setText(summary_html)

        # 8. Draw native interactive overlay rectangles
        self._draw_panel_rectangles()

    def _draw_panel_rectangles(self):
        """Draw native QGraphicsRectItem for each face and flap with cosmetic pens and badges."""
        self._canvas.clear_panels()

        s = self._session
        t = s.transform
        if not t:
            return

        M = t.get("M_affine")

        def pt2px(x_pt: float, y_pt: float) -> tuple[float, float]:
            if M is not None:
                px = M[0][0] * x_pt + M[0][1] * y_pt + M[0][2]
                py = M[1][0] * x_pt + M[1][1] * y_pt + M[1][2]
            else:
                sx = t.get("scale_x", 1.0)
                sy = t.get("scale_y", 1.0)
                ox = t.get("offset_x", 0.0)
                oy = t.get("offset_y", 0.0)
                px = x_pt * sx + ox
                py = y_pt * sy + oy
            return float(px), float(py)

        body = s.detected_body_panels
        f_idx = s.front_panel_idx if s.front_panel_idx is not None else 0

        # Map faces to body panel index (or None for lids)
        if s.is_upside_down:
            face_panel_indices = {
                "front":  f_idx,
                "left":   (f_idx + 1) % 4,
                "back":   (f_idx + 2) % 4,
                "right":  (f_idx + 3) % 4,
            }
        else:
            face_panel_indices = {
                "front":  f_idx,
                "right":  (f_idx + 1) % 4,
                "back":   (f_idx + 2) % 4,
                "left":   (f_idx + 3) % 4,
            }

        top_p = s.top_lid_panel_idx + 1 if s.top_lid_panel_idx is not None else 1
        bot_p = s.bot_lid_panel_idx + 1 if s.bot_lid_panel_idx is not None else 1
        top_attached_num = body[top_p - 1]["panel_number"] if top_p - 1 < len(body) else top_p
        bot_attached_num = body[bot_p - 1]["panel_number"] if bot_p - 1 < len(body) else bot_p

        custom_labels = {
            "top": f"TOP LID (P{top_attached_num})",
            "bottom": f"BOTTOM LID (P{bot_attached_num})",
        }

        # 1. Draw Ignored Column(s)
        if s.ignored_col_idx is not None and len(s.all_columns_info) > 4:
            c = s.all_columns_info[s.ignored_col_idx]
            px0, py0 = pt2px(c["x0"], s.grid_y[1])
            px1, py1 = pt2px(c["x1"], s.grid_y[2])
            rect = QRectF(min(px0, px1), min(py0, py1), abs(px1 - px0), abs(py1 - py0))
            self._canvas.add_panel(
                rect, face_name="ignored", panel_idx=None,
                label=f"P{c['panel_number']} (IGNORED FLAP)",
                is_ignored=True
            )

        # 2. Draw 4 Active 3D Body Panels
        for i, p in enumerate(body):
            face = None
            for f_name, b_idx in face_panel_indices.items():
                if b_idx == i:
                    face = f_name
                    break
            if face is None or face not in s.parsed_panels:
                continue
            x0, y0, x1, y1 = s.parsed_panels[face]
            px0, py0 = pt2px(x0, y0)
            px1, py1 = pt2px(x1, y1)
            rect = QRectF(min(px0, px1), min(py0, py1), abs(px1 - px0), abs(py1 - py0))
            actual_num = p.get("panel_number", i + 1)
            lbl = f"{face.upper()} (P{actual_num})"
            self._canvas.add_panel(rect, face, i, label=lbl)

        # 3. Draw Top and Bottom Lids
        for face in ("top", "bottom"):
            if face in s.parsed_panels:
                x0, y0, x1, y1 = s.parsed_panels[face]
                px0, py0 = pt2px(x0, y0)
                px1, py1 = pt2px(x1, y1)
                rect = QRectF(min(px0, px1), min(py0, py1), abs(px1 - px0), abs(py1 - py0))
                self._canvas.add_panel(rect, face, None, custom_labels.get(face))

        # 4. Draw other flaps (dust flaps) from s.all_dieline_panels
        for p_info in getattr(s, "all_dieline_panels", []):
            p_type = p_info.get("type")
            if p_type in ("top_flap", "bot_flap"):
                col_i = p_info.get("col_idx", 0)
                p_rect = p_info["rect"]
                is_main_lid = False
                for face_lid in ("top", "bottom"):
                    if face_lid in s.parsed_panels:
                        l_rect = s.parsed_panels[face_lid]
                        if abs(p_rect[0] - l_rect[0]) < 2.0 and abs(p_rect[2] - l_rect[2]) < 2.0:
                            is_main_lid = True
                            break
                if not is_main_lid:
                    px0, py0 = pt2px(p_rect[0], p_rect[1])
                    px1, py1 = pt2px(p_rect[2], p_rect[3])
                    rect = QRectF(min(px0, px1), min(py0, py1), abs(px1 - px0), abs(py1 - py0))
                    tag = "Top Flap" if p_type == "top_flap" else "Bot Flap"
                    self._canvas.add_panel(
                        rect, face_name="dust_flap", panel_idx=None,
                        label=f"P{col_i+1} {tag}",
                        is_dust_flap=True
                    )

    def _on_ignore_col_toggled(self, button, checked):
        if not checked or self._updating:
            return
        id_val = self._col_ignore_grp.id(button)
        cols = getattr(self._session, "all_columns_info", [])
        if len(cols) <= 4:
            return
        new_ignore = 0 if id_val == 0 else (len(cols) - 1)
        if self._session.ignored_col_idx != new_ignore:
            print(f"[Step 3] User selected ignored column index: {new_ignore} (Panel {new_ignore + 1})")
            self._session.ignored_col_idx = new_ignore
            self._session.front_panel_idx = None
            self._apply_front_panel(None)

    def _on_ask_ai_multi_column(self):
        from core.ai_inspector import ai_decide_multi_column_selection
        res = ai_decide_multi_column_selection(self._session)
        if res and "ignore_col_idx" in res:
            idx = int(res["ignore_col_idx"])
            self._session.ignored_col_idx = idx
            self._session.front_panel_idx = None
            self._apply_front_panel(None)
            QMessageBox.information(
                self,
                "AI Column Decision",
                f"Local AI Recommended:\n\n"
                f"• Exclude Panel {idx + 1} from 3D box body\n"
                f"• Reason: {res.get('reasoning', 'Geometric & flap analysis')}\n\n"
                f"Dieline face mapping updated!"
            )

    def _on_upside_down_toggled(self, checked: bool):
        if self._updating:
            return
        print(f"[Step 3] Upside-down toggled -> {checked}")
        self._session.is_upside_down = checked
        self._apply_front_panel(self._session.front_panel_idx)

    def _on_top_lid_changed(self, idx: int):
        if self._updating:
            return
        self._session.top_lid_panel_idx = None if idx == 0 else (idx - 1)
        self._apply_front_panel(self._session.front_panel_idx)

    def _on_bot_lid_changed(self, idx: int):
        if self._updating:
            return
        self._session.bot_lid_panel_idx = None if idx == 0 else (idx - 1)
        self._apply_front_panel(self._session.front_panel_idx)

    def _on_flip_top_toggled(self, checked: bool):
        if self._updating:
            return
        self._session.flip_top_lid_180 = checked
        _compute_panel_uvs(self._session)

    def _on_flip_bot_toggled(self, checked: bool):
        if self._updating:
            return
        self._session.flip_bot_lid_180 = checked
        _compute_panel_uvs(self._session)

    def _on_front_radio_toggled(self, button, checked):
        if not checked or self._updating:
            return
        idx = button.property("panel_idx")
        self._apply_front_panel(idx)

    def _on_canvas_panel_clicked(self, panel_idx: int):
        """Triggered when the user clicks on any panel in the dieline preview canvas."""
        print(f"[Step 3] User clicked on Panel {panel_idx + 1} -> Switching to Front face")
        self._apply_front_panel(panel_idx)

    def _apply_front_panel(self, idx: int | None):
        self._updating = True
        try:
            self._session.front_panel_idx = idx
            parse_panels(self._session, front_idx=idx)
            self._sync_ui_from_session()
        finally:
            self._updating = False

    def _swap_front_back(self):
        new_front = (self._session.front_panel_idx + 2) % 4
        self._apply_front_panel(new_front)

    def _reset_default(self):
        self._session.front_panel_idx = None
        self._apply_front_panel(None)

    def _on_dim_changed(self):
        if self._updating:
            return
        self._session.box_dims_mm = {
            "W": round(self._w_spin.value(), 1),
            "D": round(self._d_spin.value(), 1),
            "H": round(self._h_spin.value(), 1),
        }

    def _confirm(self):
        self._session.box_dims_mm = {
            "W": round(self._w_spin.value(), 1),
            "D": round(self._d_spin.value(), 1),
            "H": round(self._h_spin.value(), 1),
        }
        _compute_panel_uvs(self._session)
        self.step_done.emit()
