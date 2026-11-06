"""
Read-only zoomable overlay verification canvas.
"""
from .image_canvas import ImageCanvas


class OverlayCanvas(ImageCanvas):
    """
    Extends ImageCanvas with no extra interaction — purely for displaying
    the UV overlay verification image (zoom/pan only).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setToolTip("Scroll to zoom · Middle-drag to pan")
