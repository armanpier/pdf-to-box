"""
Step 1 (manual & rigid aligner) – Rigid Similarity / Scale-Preserving Transform.
Constrains manual handles strictly to Position (Translation), Rotation, and Scale (X/Y).
NO WARPING, NO SHEARING, NO PERSPECTIVE DISTORTION.
"""
import cv2
import numpy as np
from .session import AppSession
from .pdf_extractor import get_pdf_artwork_bounds


def compute_rigid_transform_from_handles(
    pdf_corners_pt: list,         # [(x,y), ...] 4 pts in PDF points: TL, TR, BL, BR
    handle_positions_px: list,    # [(x,y), ...] 4 pts in texture pixels: TL, TR, BL, BR
    W_tex: int,
    H_tex: int,
    uniform_scale: bool = False,
) -> tuple[dict, list]:
    """
    Given 4 corresponding point pairs (PDF dieline corners → texture pixels),
    computes a strictly orthogonal (zero-shear) transform with:
      - Translation (Position Tx, Ty)
      - Rotation (Angle θ)
      - Scale (Sx, Sy, or uniform S)
    
    Guarantees that the angle between local X and Y axes is exactly 90.0 degrees.
    Returns:
      (transform_dict, rectified_handles_px)
    """
    if len(pdf_corners_pt) != 4 or len(handle_positions_px) != 4:
        raise ValueError(
            f"Expected 4 point pairs, got {len(pdf_corners_pt)} and {len(handle_positions_px)}"
        )

    src = np.float32([[float(p[0]), float(p[1])] for p in pdf_corners_pt])
    dst = np.float32([[float(p[0]), float(p[1])] for p in handle_positions_px])

    # Dimensions and center of the PDF dieline source rectangle
    W_src = max(1.0, float(np.linalg.norm(src[1] - src[0])))
    H_src = max(1.0, float(np.linalg.norm(src[2] - src[0])))
    C_src = np.mean(src, axis=0)

    # Destination center (Translation)
    C_dst = np.mean(dst, axis=0)

    # Orientation vectors from top edge and left edge
    ux = 0.5 * ((dst[1] - dst[0]) + (dst[3] - dst[2]))
    uy = 0.5 * ((dst[2] - dst[0]) + (dst[3] - dst[1]))

    theta = float(np.arctan2(ux[1], ux[0]))
    sx = float(np.linalg.norm(ux) / W_src)
    sy = float(np.linalg.norm(uy) / H_src)

    if uniform_scale:
        s = 0.5 * (sx + sy)
        sx, sy = s, s

    if sx <= 1e-4:
        sx = 1.0
    if sy <= 1e-4:
        sy = 1.0

    cos_t = np.cos(theta)
    sin_t = np.sin(theta)

    # Pure orthogonal matrix A = R(theta) * diag(sx, sy)
    A = np.array([
        [sx * cos_t, -sy * sin_t],
        [sx * sin_t,  sy * cos_t]
    ], dtype=np.float32)

    # Translation b = C_dst - A * C_src
    b = C_dst - A @ C_src

    M = np.hstack([A, b.reshape(2, 1)])

    # Compute rectified, un-warped handle coordinates (TL, TR, BL, BR)
    rectified_pts = (A @ src.T).T + b
    rectified_handles = [(float(pt[0]), float(pt[1])) for pt in rectified_pts]

    offset_x = float(M[0, 2])
    offset_y = float(M[1, 2])
    W_tex = max(1, int(W_tex))
    H_tex = max(1, int(H_tex))

    scale_u  =  sx / W_tex
    offset_u =  offset_x / W_tex
    scale_v  = -sy / H_tex
    offset_v =  (H_tex - offset_y) / H_tex

    transform = {
        "scale_x":  sx,
        "scale_y":  sy,
        "offset_x": offset_x,
        "offset_y": offset_y,
        "scale_u":  scale_u,
        "offset_u": offset_u,
        "scale_v":  scale_v,
        "offset_v": offset_v,
        "W_tex": W_tex,
        "H_tex": H_tex,
        "inliers": 4,
        "rot_deg": float(np.degrees(theta)),
        "pos_x": float(C_dst[0]),
        "pos_y": float(C_dst[1]),
        "M_affine": M.tolist(),
    }
    return transform, rectified_handles


def compute_transform_from_params(
    pos_x: float, pos_y: float,
    rot_deg: float,
    scale_x: float, scale_y: float,
    session: AppSession,
) -> tuple[dict, list]:
    """
    Constructs the un-warped affine matrix directly from explicit parameters:
      pos_x, pos_y: pixel position of the dieline center on texture
      rot_deg: rotation angle in degrees
      scale_x, scale_y: pixels per PDF point
    """
    x0, y0, x1, y1 = get_pdf_artwork_bounds(session)
    if x1 <= x0 or y1 <= y0:
        w, h = session.pdf_width_pt, session.pdf_height_pt
        pdf_corners = [(0.0, 0.0), (w, 0.0), (0.0, h), (w, h)]
    else:
        pdf_corners = [(x0, y0), (x1, y0), (x0, y1), (x1, y1)]

    src = np.float32(pdf_corners)
    C_src = np.mean(src, axis=0)

    theta = np.radians(rot_deg)
    cos_t = np.cos(theta)
    sin_t = np.sin(theta)

    A = np.array([
        [scale_x * cos_t, -scale_y * sin_t],
        [scale_x * sin_t,  scale_y * cos_t]
    ], dtype=np.float32)

    C_dst = np.array([pos_x, pos_y], dtype=np.float32)
    b = C_dst - A @ C_src

    M = np.hstack([A, b.reshape(2, 1)])
    rectified_pts = (A @ src.T).T + b
    rectified_handles = [(float(pt[0]), float(pt[1])) for pt in rectified_pts]

    W_tex = session.transform.get("W_tex", 1) if session.transform else 1
    H_tex = session.transform.get("H_tex", 1) if session.transform else 1
    offset_x = float(M[0, 2])
    offset_y = float(M[1, 2])

    transform = {
        "scale_x":  float(scale_x),
        "scale_y":  float(scale_y),
        "offset_x": offset_x,
        "offset_y": offset_y,
        "scale_u":  scale_x / W_tex,
        "offset_u": offset_x / W_tex,
        "scale_v": -scale_y / H_tex,
        "offset_v": (H_tex - offset_y) / H_tex,
        "W_tex": W_tex,
        "H_tex": H_tex,
        "inliers": 4,
        "rot_deg": float(rot_deg),
        "pos_x": float(pos_x),
        "pos_y": float(pos_y),
        "M_affine": M.tolist(),
    }
    return transform, rectified_handles


def get_transform_params(transform: dict, session: AppSession) -> dict:
    """Extracts (pos_x, pos_y, rot_deg, scale_x, scale_y) from a transform dict."""
    if not transform:
        return {"pos_x": 0.0, "pos_y": 0.0, "rot_deg": 0.0, "scale_x": 1.0, "scale_y": 1.0}

    if "pos_x" in transform and "rot_deg" in transform:
        return {
            "pos_x": float(transform["pos_x"]),
            "pos_y": float(transform["pos_y"]),
            "rot_deg": float(transform["rot_deg"]),
            "scale_x": float(transform.get("scale_x", 1.0)),
            "scale_y": float(transform.get("scale_y", 1.0)),
        }

    M = transform.get("M_affine")
    x0, y0, x1, y1 = get_pdf_artwork_bounds(session)
    c_src = np.array([0.5 * (x0 + x1), 0.5 * (y0 + y1), 1.0], dtype=np.float32)

    if M is not None:
        M_np = np.float32(M)
        c_dst = M_np @ c_src
        pos_x, pos_y = float(c_dst[0]), float(c_dst[1])
        theta = float(np.arctan2(M_np[1, 0], M_np[0, 0]))
        sx = float(np.hypot(M_np[0, 0], M_np[0, 1]))
        sy = float(np.hypot(M_np[1, 0], M_np[1, 1]))
        if M_np[0, 0] < 0:
            sx = -sx
        if M_np[1, 1] < 0:
            sy = -sy
        rot_deg = float(np.degrees(theta))
    else:
        sx = float(transform.get("scale_x", 1.0))
        sy = float(transform.get("scale_y", 1.0))
        ox = float(transform.get("offset_x", 0.0))
        oy = float(transform.get("offset_y", 0.0))
        pos_x = float(c_src[0] * sx + ox)
        pos_y = float(c_src[1] * sy + oy)
        rot_deg = 0.0

    return {
        "pos_x": pos_x,
        "pos_y": pos_y,
        "rot_deg": rot_deg,
        "scale_x": sx,
        "scale_y": sy,
    }


def compute_transform_from_handles(
    pdf_corners_pt: list,
    handle_positions_px: list,
    W_tex: int,
    H_tex: int,
) -> dict:
    """Wrapper that enforces rigid orthogonal transform with zero warping."""
    t, _ = compute_rigid_transform_from_handles(pdf_corners_pt, handle_positions_px, W_tex, H_tex)
    return t


def update_session_from_handles(session: AppSession, handle_positions_px: list) -> tuple[dict, list]:
    """
    Called live as handles are dragged.
    Returns (transform_dict, rectified_handle_positions) so GUI can update canvas without warping.
    """
    if len(handle_positions_px) != 4:
        return session.transform or {}, handle_positions_px

    x0, y0, x1, y1 = get_pdf_artwork_bounds(session)
    if x1 <= x0 or y1 <= y0:
        w, h = session.pdf_width_pt, session.pdf_height_pt
        pdf_corners = [(0.0, 0.0), (w, 0.0), (0.0, h), (w, h)]
    else:
        pdf_corners = [(x0, y0), (x1, y0), (x0, y1), (x1, y1)]

    W_tex = session.transform.get("W_tex", 1) if session.transform else 1
    H_tex = session.transform.get("H_tex", 1) if session.transform else 1

    try:
        transform, rectified = compute_rigid_transform_from_handles(
            pdf_corners, handle_positions_px, W_tex, H_tex
        )
        session.transform = transform
        session.align_method = "manual"
        session.align_quality = 1.0
        return transform, rectified
    except Exception as exc:
        print(f"[Manual Align Error] {exc}")
        return session.transform or {}, handle_positions_px
