"""
Base zoomable/pannable QGraphicsView for displaying images.
"""
from PyQt6.QtWidgets import QGraphicsView, QGraphicsScene
from PyQt6.QtGui import QPixmap, QImage, QWheelEvent, QMouseEvent, QPainter
from PyQt6.QtCore import Qt, QRectF
import numpy as np
import cv2


def numpy_to_qpixmap(img_bgr: np.ndarray) -> QPixmap:
    """Convert a BGR numpy array to QPixmap."""
    if img_bgr is None:
        return QPixmap()
    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    h, w, ch = img_rgb.shape
    qi = QImage(img_rgb.data, w, h, ch * w, QImage.Format.Format_RGB888).copy()
    return QPixmap.fromImage(qi)


class ImageCanvas(QGraphicsView):
    """
    A QGraphicsView that displays an image and supports:
    - Mouse-wheel zoom
    - Middle-button / Space+drag panning
    - fit_to_view() to reset zoom
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._pixmap_item = None
        self._panning = False
        self._pan_start = None
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self.setStyleSheet("background: #1e1e1e; border: 1px solid #444;")

    def load_image(self, img_bgr: np.ndarray):
        """Load a BGR numpy array into the canvas."""
        self.load_pixmap(numpy_to_qpixmap(img_bgr))

    def load_pixmap(self, pixmap: QPixmap):
        self._scene.clear()
        self._pixmap_item = self._scene.addPixmap(pixmap)
        self._scene.setSceneRect(QRectF(pixmap.rect()))
        self._pixmap_item.setZValue(0)
        self.fit_to_view()

    def load_file(self, path: str):
        pm = QPixmap(path)
        if not pm.isNull():
            self.load_pixmap(pm)

    def fit_to_view(self):
        if self._pixmap_item:
            self.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def wheelEvent(self, event: QWheelEvent):
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._pan_start = event.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._panning and self._pan_start is not None:
            delta = event.position().toPoint() - self._pan_start
            self._pan_start = event.position().toPoint()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - delta.x()
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - delta.y()
            )
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
        else:
            super().mouseReleaseEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fit_to_view()
