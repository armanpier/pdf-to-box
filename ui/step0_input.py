"""
Step 0 – File input panel.
User selects PDF dieline and diffuse texture, then triggers extraction.
"""
import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QFileDialog, QGroupBox, QMessageBox,
)
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QDragEnterEvent, QDropEvent


class _FilePicker(QWidget):
    """A labelled file path row with browse button and drag-drop support."""

    path_changed = pyqtSignal(str)

    def __init__(self, label: str, filter_str: str, parent=None):
        super().__init__(parent)
        self._filter = filter_str
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        lbl = QLabel(f"<b>{label}</b>")
        layout.addWidget(lbl)

        row = QHBoxLayout()
        self._edit = QLineEdit()
        self._edit.setPlaceholderText("Drag & drop or click Browse…")
        self._edit.setAcceptDrops(True)
        self._edit.textChanged.connect(self.path_changed)
        row.addWidget(self._edit)

        btn = QPushButton("Browse…")
        btn.setFixedWidth(90)
        btn.clicked.connect(self._browse)
        row.addWidget(btn)
        layout.addLayout(row)

        self.setAcceptDrops(True)

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select file", "", self._filter)
        if path:
            self._edit.setText(path)

    def path(self) -> str:
        return self._edit.text().strip()

    def set_path(self, p: str):
        self._edit.setText(p)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        if urls:
            self._edit.setText(urls[0].toLocalFile())


class Step0Input(QWidget):
    """Step 0: select PDF + texture and run initial extraction."""

    step_done = pyqtSignal()   # emitted when extraction succeeds

    def __init__(self, session, parent=None):
        super().__init__(parent)
        self._session = session
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(20)
        root.setContentsMargins(30, 30, 30, 30)

        title = QLabel("<h2>① Select Input Files</h2>")
        root.addWidget(title)

        desc = QLabel(
            "Provide the prepress vector PDF (containing the dieline / diecutter layer) "
            "and the diffuse texture image for this packaging."
        )
        desc.setWordWrap(True)
        root.addWidget(desc)

        grp = QGroupBox("Input files")
        grp_layout = QVBoxLayout(grp)
        grp_layout.setSpacing(16)

        self._pdf_picker = _FilePicker("PDF Dieline", "PDF files (*.pdf)")
        self._pdf_picker.path_changed.connect(self._on_path_changed)
        grp_layout.addWidget(self._pdf_picker)

        self._tex_picker = _FilePicker(
            "Diffuse Texture", "Image files (*.jpg *.jpeg *.png *.tif *.tiff)"
        )
        self._tex_picker.path_changed.connect(self._on_path_changed)
        grp_layout.addWidget(self._tex_picker)

        root.addWidget(grp)
        root.addStretch()

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._next_btn = QPushButton("Extract PDF  →")
        self._next_btn.setFixedHeight(40)
        self._next_btn.setEnabled(False)
        self._next_btn.clicked.connect(self._run)
        btn_row.addWidget(self._next_btn)
        root.addLayout(btn_row)

    def _on_path_changed(self):
        ready = bool(self._pdf_picker.path() and self._tex_picker.path())
        self._next_btn.setEnabled(ready)

    def _run(self):
        from core.pdf_extractor import open_pdf, extract_diecutter_texture, find_dieline_drawings

        pdf  = self._pdf_picker.path()
        tex  = self._tex_picker.path()

        if not os.path.isfile(pdf):
            QMessageBox.warning(self, "Missing file", f"PDF not found:\n{pdf}")
            return
        if not os.path.isfile(tex):
            QMessageBox.warning(self, "Missing file", f"Texture not found:\n{tex}")
            return

        self._session.pdf_path     = pdf
        self._session.texture_path = tex
        self._session.output_dir   = os.path.dirname(os.path.abspath(pdf))

        try:
            open_pdf(self._session)
            extract_diecutter_texture(self._session)
            find_dieline_drawings(self._session)
        except Exception as exc:
            QMessageBox.critical(self, "Extraction error", str(exc))
            return

        self.step_done.emit()
