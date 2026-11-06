"""
Step 2 – Render UV overlay verification image.
Draws dieline paths (cyan cuts, yellow folds) on top of the diffuse texture.
Uses proportional thickness and high-contrast backing so lines are bold and visible
at any display resolution or downsampled zoom level.
"""
import os
from math import comb

import cv2
import numpy as np

from .session import AppSession

# BGR colours
_CYAN   = (255, 255,   0)   # RGB cyan   → BGR
_YELLOW = (  0, 255, 255)   # RGB yellow → BGR
_DARK   = ( 20,  20,  20)   # Contrast outline backing


def _bernstein(n: int, i: int, t: float) -> float:
    return comb(n, i) * (t ** i) * ((1 - t) ** (n - i))


def render_uv_overlay(session: AppSession, output_path: str | None = None) -> str:
    """
    Render the UV wireframe overlay and save to *output_path*.
    Returns the saved path.
    """
    if output_path is None:
        output_path = os.path.join(session.output_dir, "uv_overlay_check.png")

    diffuse = cv2.imread(session.texture_path)
    if diffuse is None:
        raise FileNotFoundError(f"Cannot load texture: {session.texture_path}")
    overlay = diffuse.copy()
    H_tex, W_tex = overlay.shape[:2]

    # Ensure grid creases and panel folds are detected
    if not session.grid_x or not session.grid_y or not session.detected_body_panels:
        from .panel_parser import parse_panels
        parse_panels(session)

    t = session.transform
    M = t.get("M_affine")

    def pt2px(x: float, y: float) -> tuple[int, int]:
        if M is not None:
            px = M[0][0] * x + M[0][1] * y + M[0][2]
            py = M[1][0] * x + M[1][1] * y + M[1][2]
        else:
            px = x * t["scale_x"] + t["offset_x"]
            py = y * t["scale_y"] + t["offset_y"]
        return int(round(px)), int(round(py))

    # Line thickness scaled proportionally to texture dimensions
    # For a 5000x5000 image, thick = 8 px, outline = 12 px
    thick = max(4, int(round(max(W_tex, H_tex) / 600)))
    outline_thick = thick + 4

    # ── 1. Draw dieline cut paths (cyan cuts with dark border) ───────────────
    for d in session.dieline_drawings:
        for item in d.get("items", []):
            itype = item[0]
            if itype == "l":
                p1, p2 = pt2px(item[1].x, item[1].y), pt2px(item[2].x, item[2].y)
                cv2.line(overlay, p1, p2, _DARK, outline_thick)
                cv2.line(overlay, p1, p2, _CYAN, thick)
            elif itype == "re":
                r = item[1]
                p1, p2 = pt2px(r.x0, r.y0), pt2px(r.x1, r.y1)
                cv2.rectangle(overlay, p1, p2, _DARK, outline_thick)
                cv2.rectangle(overlay, p1, p2, _CYAN, thick)
            elif itype == "c":
                pts = [item[1], item[2], item[3], item[4]]
                curve = [
                    pt2px(
                        sum(_bernstein(3, i, tv) * pts[i].x for i in range(4)),
                        sum(_bernstein(3, i, tv) * pts[i].y for i in range(4)),
                    )
                    for tv in np.linspace(0, 1, 16)
                ]
                for i in range(len(curve) - 1):
                    cv2.line(overlay, curve[i], curve[i + 1], _DARK, outline_thick)
                    cv2.line(overlay, curve[i], curve[i + 1], _CYAN, thick)

    # ── 2. Draw panel fold lines (yellow with dark border) ───────────────────
    if session.grid_x and session.grid_y:
        y_top_hinge = session.grid_y[1]
        y_bot_hinge = session.grid_y[2]
        x_min = session.grid_x[0]
        x_max = session.grid_x[-1]

        # Horizontal top hinge crease across all panels
        p_th1, p_th2 = pt2px(x_min, y_top_hinge), pt2px(x_max, y_top_hinge)
        cv2.line(overlay, p_th1, p_th2, _DARK, outline_thick + 2)
        cv2.line(overlay, p_th1, p_th2, _YELLOW, thick + 2)

        # Horizontal bottom hinge crease across all panels
        p_bh1, p_bh2 = pt2px(x_min, y_bot_hinge), pt2px(x_max, y_bot_hinge)
        cv2.line(overlay, p_bh1, p_bh2, _DARK, outline_thick + 2)
        cv2.line(overlay, p_bh1, p_bh2, _YELLOW, thick + 2)

        # Vertical interior panel fold creases (between top and bottom hinge)
        for x in session.grid_x[1:-1]:
            p1, p2 = pt2px(x, y_top_hinge), pt2px(x, y_bot_hinge)
            cv2.line(overlay, p1, p2, _DARK, outline_thick + 2)
            cv2.line(overlay, p1, p2, _YELLOW, thick + 2)

        # Flap tuck fold lines if present
        if session.detected_body_panels:
            for p in session.detected_body_panels:
                top_flap_h = p.get("top_flap_h_mm", 0)
                if top_flap_h > 20:  # Major lid with tuck flap
                    ty = p.get("top_y", y_top_hinge)
                    p1, p2 = pt2px(p["x0"], ty), pt2px(p["x1"], ty)
                    if abs(p1[1] - p_th1[1]) > 50:
                        cv2.line(overlay, p1, p2, _DARK, outline_thick)
                        cv2.line(overlay, p1, p2, _YELLOW, thick)

                bot_flap_h = p.get("bot_flap_h_mm", 0)
                if bot_flap_h > 20:
                    by = p.get("bot_y", y_bot_hinge)
                    p1, p2 = pt2px(p["x0"], by), pt2px(p["x1"], by)
                    if abs(p1[1] - p_bh1[1]) > 50:
                        cv2.line(overlay, p1, p2, _DARK, outline_thick)
                        cv2.line(overlay, p1, p2, _YELLOW, thick)

    # ── 3. High-contrast legend badge in top-left ────────────────────────────
    badge_scale = max(1.0, W_tex / 2000.0)
    font_scale = 1.0 * badge_scale
    l_thick = max(2, int(round(2 * badge_scale)))
    pad = int(round(25 * badge_scale))
    lh = int(round(45 * badge_scale))

    # Dark background pill for legend
    bg_w = int(round(360 * badge_scale))
    bg_h = int(round(120 * badge_scale))
    cv2.rectangle(overlay, (pad - 10, pad - 10), (pad + bg_w, pad + bg_h), (20, 20, 20), -1)
    cv2.rectangle(overlay, (pad - 10, pad - 10), (pad + bg_w, pad + bg_h), (80, 80, 80), max(1, int(badge_scale)))

    cv2.putText(overlay, "CUTS  (CYAN)",   (pad, pad + lh),     cv2.FONT_HERSHEY_SIMPLEX, font_scale, _CYAN,   l_thick)
    cv2.putText(overlay, "FOLDS (YELLOW)", (pad, pad + lh * 2), cv2.FONT_HERSHEY_SIMPLEX, font_scale, _YELLOW, l_thick)

    cv2.imwrite(output_path, overlay)
    session.overlay_path = output_path
    print(f"[Step 2] UV overlay saved: {output_path} (thick={thick}px, folds drawn)")
    return output_path
