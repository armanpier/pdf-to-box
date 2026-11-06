"""
Alignment canvas: shows the diffuse texture as background, overlays the
(warped) PDF outline, and provides draggable corner handles constrained strictly
to position, rotation, and scale (NO WARPING / NO SHEARING).
"""
from PyQt6.QtWidgets import QGraphicsView, QGraphicsScene, QGraphicsEllipseItem, QGraphicsItem, QGraphicsPolygonItem
from PyQt6.QtGui import QPixmap, QImage, QPen, QBrush, QColor, QPainter, QWheelEvent, QPolygonF
from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal
import numpy as np
import cv2

from .image_canvas import numpy_to_qpixmap


# ── Draggable corner handle ───────────────────────────────────────────────────

class AlignHandle(QGraphicsEllipseItem):
    """A draggable corner handle drawn as a filled circle."""

    RADIUS = 12

    def __init__(self, label: str, canvas: "AlignCanvas"):
        r = self.RADIUS
        super().__init__(-r, -r, 2 * r, 2 * r)
        self._canvas = canvas
        self._label  = label
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations, True)
        self.setZValue(20)
        self.setBrush(QBrush(QColor("#FF6600")))
        self.setPen(QPen(QColor("white"), 2.5))
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self.setToolTip(f"Drag to adjust corner {label} (Strictly maintains rectangle - No Warping)")

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            if hasattr(self._canvas, "_on_handle_moved"):
                self._canvas._on_handle_moved()
        return super().itemChange(change, value)


# ── Alignment canvas ──────────────────────────────────────────────────────────

class AlignCanvas(QGraphicsView):
    """
    Three-layer canvas:
      Layer 0: diffuse texture
      Layer 1: semi-transparent warped PDF overlay
      Layer 2: bounding box polygon outline
      Layer 3: 4 AlignHandle items at corners
    Emits handles_changed(list) with 4 [(x,y)] texture-pixel positions whenever a handle moves.
    """

    handles_changed = pyqtSignal(list)   # list of 4 (x, y) in texture pixels

    HANDLE_LABELS = ["TL", "TR", "BL", "BR"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet("background: #1e1e1e; border: 1px solid #444;")

        self._tex_item     = None
        self._overlay_item = None
        self._box_polygon  = None
        self._handles: list[AlignHandle] = []
        self._handles_enabled = False
        self._block_handle_signals = False
        self._cached_handle_positions = None
        self._W_tex = 1
        self._H_tex = 1

    # ── Public API ────────────────────────────────────────────────────────────

    def load_texture(self, img_bgr: np.ndarray):
        """Load diffuse texture as background."""
        self._W_tex, self._H_tex = img_bgr.shape[1], img_bgr.shape[0]
        pm = numpy_to_qpixmap(img_bgr)
        self._block_handle_signals = True
        try:
            self._scene.clear()
            self._handles.clear()
            self._box_polygon = None
            self._handles_enabled = False
            self._tex_item     = self._scene.addPixmap(pm)
            self._overlay_item = None
            self._tex_item.setZValue(0)
            self._scene.setSceneRect(QRectF(pm.rect()))
            self.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        finally:
            self._block_handle_signals = False

    def set_pdf_overlay(self, warped_pdf_bgr: np.ndarray, alpha: float = 0.45):
        """Overlay the warped PDF on the texture with the given alpha (0-1)."""
        if warped_pdf_bgr is None:
            return
        tex_h, tex_w = self._H_tex, self._W_tex
        overlay = cv2.resize(warped_pdf_bgr, (tex_w, tex_h))
        pm = numpy_to_qpixmap(overlay)
        if self._overlay_item is not None:
            self._scene.removeItem(self._overlay_item)
        self._overlay_item = self._scene.addPixmap(pm)
        self._overlay_item.setZValue(1)
        self._overlay_item.setOpacity(alpha)

    def enable_handles(self, initial_positions: list | None = None):
        """
        Show 4 draggable corner handles.
        *initial_positions*: [(x,y), ...] TL,TR,BL,BR in texture pixels.
        """
        self._block_handle_signals = True
        try:
            for h in self._handles:
                self._scene.removeItem(h)
            self._handles.clear()

            if initial_positions is None or len(initial_positions) != 4:
                if self._cached_handle_positions and len(self._cached_handle_positions) == 4:
                    initial_positions = self._cached_handle_positions
                else:
                    w, h = self._W_tex, self._H_tex
                    initial_positions = [(0.0, 0.0), (float(w), 0.0), (0.0, float(h)), (float(w), float(h))]

            for label, (x, y) in zip(self.HANDLE_LABELS, initial_positions):
                handle = AlignHandle(label, self)
                handle.setPos(QPointF(float(x), float(y)))
                self._scene.addItem(handle)
                self._handles.append(handle)

            self._cached_handle_positions = [(float(x), float(y)) for x, y in initial_positions]
            self._handles_enabled = True
            self._update_box_polygon(initial_positions)
        finally:
            self._block_handle_signals = False

    def disable_handles(self):
        self._block_handle_signals = True
        try:
            for h in self._handles:
                self._scene.removeItem(h)
            self._handles.clear()
            if self._box_polygon is not None:
                self._scene.removeItem(self._box_polygon)
                self._box_polygon = None
            self._handles_enabled = False
        finally:
            self._block_handle_signals = False

    def get_handle_positions(self) -> list:
        """Return [(x, y), ...] TL,TR,BL,BR in texture pixel coords."""
        return [(h.pos().x(), h.pos().y()) for h in self._handles]

    def set_handle_positions(self, positions: list):
        """Move handles to given [(x,y), ...] positions without firing signals."""
        if len(positions) != 4 or len(self._handles) != 4:
            return
        self._block_handle_signals = True
        try:
            for handle, (x, y) in zip(self._handles, positions):
                handle.setPos(QPointF(float(x), float(y)))
            self._cached_handle_positions = [(float(x), float(y)) for x, y in positions]
            self._update_box_polygon(positions)
        finally:
            self._block_handle_signals = False

    def reset_handles_to_transform(self, transform: dict, session=None):
        """
        Compute corners matching the auto-computed transform using M_affine directly.
        Guarantees accurate position and rotation for the handles.
        """
        if not transform:
            return

        M = transform.get("M_affine")
        pdf_corners = []

        if session is not None:
            from core.pdf_extractor import get_pdf_artwork_bounds
            x0, y0, x1, y1 = get_pdf_artwork_bounds(session)
            if x1 > x0 and y1 > y0:
                pdf_corners = [(x0, y0), (x1, y0), (x0, y1), (x1, y1)]

        if not pdf_corners:
            pw = transform.get("pdf_w_pt", self._W_tex)
            ph = transform.get("pdf_h_pt", self._H_tex)
            pdf_corners = [(0.0, 0.0), (float(pw), 0.0), (0.0, float(ph)), (float(pw), float(ph))]

        positions = []
        if M is not None:
            M_mat = np.float32(M)
            for x, y in pdf_corners:
                px = M_mat[0, 0] * x + M_mat[0, 1] * y + M_mat[0, 2]
                py = M_mat[1, 0] * x + M_mat[1, 1] * y + M_mat[1, 2]
                positions.append((float(px), float(py)))
        else:
            sx = transform.get("scale_x", 1.0)
            sy = transform.get("scale_y", 1.0)
            ox = transform.get("offset_x", 0.0)
            oy = transform.get("offset_y", 0.0)
            for x, y in pdf_corners:
                positions.append((float(x * sx + ox), float(y * sy + oy)))

        self._cached_handle_positions = positions
        if self._handles_enabled and len(self._handles) == 4:
            self.set_handle_positions(positions)

    def _update_box_polygon(self, positions: list):
        """Draw an orange outline connecting TL -> TR -> BR -> BL -> TL."""
        if len(positions) != 4:
            return
        tl, tr, bl, br = positions
        poly = QPolygonF([
            QPointF(tl[0], tl[1]),
            QPointF(tr[0], tr[1]),
            QPointF(br[0], br[1]),
            QPointF(bl[0], bl[1]),
        ])
        if self._box_polygon is None:
            self._box_polygon = self._scene.addPolygon(
                poly,
                QPen(QColor("#FF7700"), 2, Qt.PenStyle.DashLine),
                QBrush(QColor(255, 119, 0, 25))
            )
            self._box_polygon.setZValue(15)
        else:
            self._box_polygon.setPolygon(poly)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _on_handle_moved(self):
        if getattr(self, "_block_handle_signals", False) or not self._handles_enabled:
            return
        positions = self.get_handle_positions()
        if len(positions) == 4:
            self._cached_handle_positions = positions
            self.handles_changed.emit(positions)

    def wheelEvent(self, event: QWheelEvent):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._tex_item:
            self.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
