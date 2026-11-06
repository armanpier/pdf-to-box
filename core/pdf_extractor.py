"""
Step 0 – PDF rasterization and dieline layer detection.
"""
import os
import pymupdf
from .session import AppSession


def open_pdf(session: AppSession) -> None:
    """Open the PDF file and populate metadata in session."""
    session.pdf_doc = pymupdf.open(session.pdf_path)
    page = session.pdf_doc[0]
    session.pdf_width_pt = page.rect.width
    session.pdf_height_pt = page.rect.height
    session.output_dir = session.output_dir or os.path.dirname(os.path.abspath(session.pdf_path))


def extract_diecutter_texture(session: AppSession, dpi: int = 300) -> str:
    """
    Step 0a: Rasterize PDF page → diecutter_texture.png at *dpi* resolution.
    Returns the saved path.
    """
    if session.pdf_doc is None:
        open_pdf(session)
    page = session.pdf_doc[0]
    pix = page.get_pixmap(dpi=dpi)
    out_path = os.path.join(session.output_dir, "diecutter_texture.png")
    pix.save(out_path)
    session.diecutter_texture_path = out_path
    print(f"[Step 0] Diecutter texture: {out_path} ({pix.width}×{pix.height})")
    return out_path


def find_dieline_drawings(session: AppSession) -> tuple:
    """
    Step 0b: Auto-detect dieline spot-colours (both Cut and Crease stroke layers)
    and collect matching technical vector paths.
    """
    page = session.pdf_doc[0]
    drawings = page.get_drawings()

    stroke_counts: dict[tuple, int] = {}
    for d in drawings:
        sc = d.get("color")
        if sc is None or len(sc) < 3:
            continue
        r, g, b = round(sc[0], 2), round(sc[1], 2), round(sc[2], 2)
        is_gray = abs(r - g) < 0.04 and abs(g - b) < 0.04
        is_white = (r > 0.95 and g > 0.95 and b > 0.95)
        if not is_gray and not is_white:
            stroke_counts[(r, g, b)] = stroke_counts.get((r, g, b), 0) + 1

    # Keep top technical stroke spot colors (Cut + Crease)
    sorted_colors = [c for c, cnt in sorted(stroke_counts.items(), key=lambda x: -x[1]) if cnt >= 4]
    if not sorted_colors:
        sorted_colors = [(0.0, 0.66, 0.32)]

    session.dieline_color = sorted_colors[0]
    active_colors = sorted_colors[:3]  # Allow Cut + Crease + Bleed/Reg stroke colors

    dieline = []
    for d in drawings:
        sc = d.get("color")
        if sc is None or len(sc) < 3:
            continue
        if any(all(abs(sc[i] - c[i]) < 0.12 for i in range(3)) for c in active_colors):
            dieline.append(d)

    session.dieline_drawings = dieline
    print(f"[Step 0] Detected primary dieline stroke colour: {session.dieline_color}")
    print(f"[Step 0] {len(dieline)} dieline paths collected across active stroke colors: {active_colors}")
    return dieline, session.dieline_color


def get_pdf_artwork_bounds(session: AppSession) -> tuple:
    """
    Return (x0, y0, x1, y1) bounding box of the main dieline net in PDF points,
    filtering out page-border frames and isolated corner text legends.
    """
    if not session.dieline_drawings:
        return (0.0, 0.0, session.pdf_width_pt, session.pdf_height_pt)

    pw, ph = session.pdf_width_pt, session.pdf_height_pt
    valid_rects = []
    for d in session.dieline_drawings:
        r = d.get("rect")
        if r is None or r.is_empty:
            continue
        # Ignore full-page border frames (>94% of page width & height)
        if r.width > pw * 0.94 and r.height > ph * 0.94:
            continue
        # Ignore tiny isolated specks (<2 pt)
        if r.width < 2.0 and r.height < 2.0:
            continue
        valid_rects.append(r)

    if not valid_rects:
        valid_rects = [d["rect"] for d in session.dieline_drawings if d.get("rect")]

    # Filter out outlier legend boxes far from the median center
    cx_med = sorted([(r.x0 + r.x1) * 0.5 for r in valid_rects])[len(valid_rects) // 2]
    cy_med = sorted([(r.y0 + r.y1) * 0.5 for r in valid_rects])[len(valid_rects) // 2]

    core_rects = [
        r for r in valid_rects
        if abs((r.x0 + r.x1) * 0.5 - cx_med) < pw * 0.45
        and abs((r.y0 + r.y1) * 0.5 - cy_med) < ph * 0.45
    ] or valid_rects

    x0 = min(r.x0 for r in core_rects)
    y0 = min(r.y0 for r in core_rects)
    x1 = max(r.x1 for r in core_rects)
    y1 = max(r.y1 for r in core_rects)
    return (x0, y0, x1, y1)
