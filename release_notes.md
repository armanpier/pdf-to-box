# PDF to Box Package Builder v1.0.0

First public release of **PDF to Box**, a deterministic desktop application and automation pipeline for generating photorealistic 3D folding carton packaging boxes in **Autodesk 3ds Max 2024** directly from prepress vector PDFs and diffuse texture maps.

## Highlights
- **Zero Viewport Guesswork**: Replaces perspective-skewed 3D viewport screenshots with closed-form mathematical affine alignment.
- **5-Step Guided Pipeline**:
  - **Step 0**: High-resolution (300 DPI) diecutter vector and spot dieline extraction via PyMuPDF.
  - **Step 1**: Multi-scale texture calibration (White-crop bounding box, SIFT keypoints, and 4-corner orthogonal manual handles).
  - **Step 2**: 2D UV wireframe overlay verification (Cyan cut lines, Yellow crease lines).
  - **Step 3**: Visual face mapping & millimeter dimension calculation ($W \times D \times H$).
  - **Step 4**: One-click 3ds Max 2024 automated generation via Win32 IPC bridge with flat planar UV locking, quad chamfering ($0.4\text{ mm}$), and PhysicalMaterial.
- **Portable Asset Linking**: Automatically saves `.max` scene files and texture bitmaps directly into the source PDF's folder.
- **Multiple Interfaces**:
  - Full desktop PyQt6 GUI (`main.py` / `run_app.bat`)
  - Headless CLI runner (`cli.py`) for batch processing and CI
  - Antigravity AI Agent Skill (`SKILL.md`)

## Included Assets
- `pdf-to-box-v1.0.0.zip`: Clean standalone distribution ready to run.
- `pdf_to_box.rar`: Compressed Windows package archive.
