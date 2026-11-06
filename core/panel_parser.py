"""
Step 3 – Parse dieline panel regions and map to 3D UV coordinates.
Supports arbitrary column counts (4, 5, or more) and extracts 100% of all flat
dieline net panels (bodies, top flaps, bottom flaps, and extra closure flaps).
"""
import numpy as np
import cv2
from .session import AppSession

_PT_PER_MM = 72.0 / 25.4   # 1 mm = 2.834645 pt


def _cluster(values: list[float], tol: float = 3.0) -> list[float]:
    """Average nearby coordinate values within *tol* points."""
    if not values:
        return []
    vals = sorted(set(round(v, 2) for v in values))
    clusters = [[vals[0]]]
    for v in vals[1:]:
        if v - clusters[-1][-1] <= tol:
            clusters[-1].append(v)
        else:
            clusters.append([v])
    return [float(np.mean(c)) for c in clusters]


def find_grid_lines(session: AppSession) -> tuple[list, list]:
    """
    Extract the primary column (x) and row (y) panel boundaries from the dieline paths
    by aggregating collinear segments, merging intervals, and ranking by span.
    """
    raw_v_segs = []  # (x, y_min, y_max)
    raw_h_segs = []  # (y, x_min, x_max)

    for d in session.dieline_drawings:
        for item in d.get("items", []):
            itype = item[0]
            if itype == "l":
                p1, p2 = item[1], item[2]
                if abs(p1.x - p2.x) < 1.5 and abs(p1.y - p2.y) > 2.0:
                    raw_v_segs.append((0.5 * (p1.x + p2.x), min(p1.y, p2.y), max(p1.y, p2.y)))
                elif abs(p1.y - p2.y) < 1.5 and abs(p1.x - p2.x) > 2.0:
                    raw_h_segs.append((0.5 * (p1.y + p2.y), min(p1.x, p2.x), max(p1.x, p2.x)))
            elif itype == "re":
                r = item[1]
                raw_v_segs.append((r.x0, r.y0, r.y1))
                raw_v_segs.append((r.x1, r.y0, r.y1))
                raw_h_segs.append((r.y0, r.x0, r.x1))
                raw_h_segs.append((r.y1, r.x0, r.x1))

    def _cluster_and_sum_spans(segs, tol=8.0):
        if not segs:
            return []
        segs.sort(key=lambda s: s[0])
        groups = [[segs[0]]]
        for s in segs[1:]:
            if abs(s[0] - np.mean([g[0] for g in groups[-1]])) <= tol:
                groups[-1].append(s)
            else:
                groups.append([s])

        results = []
        for g in groups:
            avg_pos = float(np.mean([s[0] for s in g]))
            intervals = sorted([(s[1], s[2]) for s in g])
            merged = [list(intervals[0])]
            for start, end in intervals[1:]:
                if start <= merged[-1][1] + 5.0:
                    merged[-1][1] = max(merged[-1][1], end)
                else:
                    merged.append([start, end])
            total_len = sum(end - start for start, end in merged)
            results.append((avg_pos, total_len, merged[0][0], merged[-1][1]))
        return sorted(results, key=lambda r: -r[1])

    clustered_y = _cluster_and_sum_spans(raw_h_segs, tol=8.0)
    clustered_x = _cluster_and_sum_spans(raw_v_segs, tol=8.0)

    if len(clustered_y) >= 2:
        hinges = sorted([clustered_y[0][0], clustered_y[1][0]])
        y_top_hinge, y_bot_hinge = hinges[0], hinges[1]
    else:
        y_top_hinge = session.pdf_height_pt * 0.25
        y_bot_hinge = session.pdf_height_pt * 0.75

    all_ys = [s[1] for s in raw_v_segs] + [s[2] for s in raw_v_segs] + [s[0] for s in raw_h_segs]
    y_min = min(all_ys) if all_ys else 0.0
    y_max = max(all_ys) if all_ys else session.pdf_height_pt
    grid_y = [y_min, y_top_hinge, y_bot_hinge, y_max]

    # Keep all major vertical column splits with span >= 15% of page height (or top 7)
    min_span = session.pdf_height_pt * 0.15
    valid_x = [c for c in clustered_x if c[1] >= min_span]
    if len(valid_x) < 5 and len(clustered_x) >= 5:
        valid_x = clustered_x[:7]

    top_x_clusters = sorted(valid_x[:8], key=lambda item: item[0])
    grid_x = [c[0] for c in top_x_clusters]

    session.grid_x = grid_x
    session.grid_y = grid_y
    print(f"[Step 3] Grid: {len(grid_x)} column splits ({[round(x, 1) for x in grid_x]}), {len(grid_y)} row splits ({[round(y, 1) for y in grid_y]})")
    return grid_x, grid_y


def _auto_detect_lid_panels(session: AppSession, body: list, y_top_hinge: float, y_bot_hinge: float) -> tuple[int, int]:
    """Detect which active panels have the primary top lid and bottom lid."""
    try:
        import os
        if session.texture_path and os.path.isfile(session.texture_path) and session.transform:
            diffuse = cv2.imread(session.texture_path)
            if diffuse is not None:
                t = session.transform
                H_tex, W_tex = diffuse.shape[:2]
                M = t.get("M_affine")

                def pt2px_local(x, y):
                    if M is not None:
                        px = M[0][0] * x + M[0][1] * y + M[0][2]
                        py = M[1][0] * x + M[1][1] * y + M[1][2]
                    else:
                        px = x * t.get("scale_x", 1.0) + t.get("offset_x", 0.0)
                        py = y * t.get("scale_y", 1.0) + t.get("offset_y", 0.0)
                    return int(round(px)), int(round(py))

                top_scores = []
                bot_scores = []

                for p in body:
                    x0, x1 = p["x0"], p["x1"]
                    p_top0 = pt2px_local(x0, y_top_hinge)
                    p_top1 = pt2px_local(x1, y_top_hinge - 150.0)
                    xmin_t, xmax_t = max(0, min(p_top0[0], p_top1[0])), min(W_tex, max(p_top0[0], p_top1[0]))
                    ymin_t, ymax_t = max(0, min(p_top0[1], p_top1[1])), min(H_tex, max(p_top0[1], p_top1[1]))
                    top_crop = diffuse[ymin_t:ymax_t, xmin_t:xmax_t] if (xmax_t > xmin_t and ymax_t > ymin_t) else np.array([])

                    p_bot0 = pt2px_local(x0, y_bot_hinge)
                    p_bot1 = pt2px_local(x1, y_bot_hinge + 150.0)
                    xmin_b, xmax_b = max(0, min(p_bot0[0], p_bot1[0])), min(W_tex, max(p_bot0[0], p_bot1[0]))
                    ymin_b, ymax_b = max(0, min(p_bot0[1], p_bot1[1])), min(H_tex, max(p_bot0[1], p_bot1[1]))
                    bot_crop = diffuse[ymin_b:ymax_b, xmin_b:xmax_b] if (xmax_b > xmin_b and ymax_b > ymin_b) else np.array([])

                    ts = int(np.sum(cv2.cvtColor(top_crop, cv2.COLOR_BGR2GRAY) < 240)) if top_crop.size else 0
                    bs = int(np.sum(cv2.cvtColor(bot_crop, cv2.COLOR_BGR2GRAY) < 240)) if bot_crop.size else 0
                    top_scores.append(ts)
                    bot_scores.append(bs)

                best_top = int(np.argmax(top_scores))
                best_bot = int(np.argmax(bot_scores))
                if max(top_scores) > 200000:
                    return best_top, best_bot
    except Exception:
        pass

    top_flaps = [p.get("top_flap_h_mm", 0) for p in getattr(session, "detected_body_panels", [])] or [0] * len(body)
    bot_flaps = [p.get("bot_flap_h_mm", 0) for p in getattr(session, "detected_body_panels", [])] or [0] * len(body)
    return int(np.argmax(top_flaps)), int(np.argmax(bot_flaps))


def parse_panels(session: AppSession, front_idx: int | None = None) -> dict:
    """
    Parse panel regions across ALL columns (4, 5, or more).
    Extracts 100% of all body panels and flaps into `session.all_dieline_panels`.
    If >4 columns, selects 4 active perimeter walls (allowing user or AI to ignore extra flaps).
    """
    grid_x, grid_y = find_grid_lines(session)

    if len(grid_x) < 2:
        w = session.pdf_width_pt
        grid_x = [0.0, w * 0.25, w * 0.5, w * 0.75, w]
    if len(grid_y) < 4:
        h = session.pdf_height_pt
        grid_y = [0.0, h * 0.18, h * 0.82, h]

    y_top_hinge = grid_y[1]
    y_bot_hinge = grid_y[2]

    # Extract all raw columns between consecutive x splits
    raw_cols = []
    for i in range(len(grid_x) - 1):
        x0, x1 = grid_x[i], grid_x[i + 1]
        w_pt = x1 - x0
        w_mm = w_pt / _PT_PER_MM
        if w_mm >= 15.0:  # Ignore tiny margin slivers (< 15mm)
            raw_cols.append({"col_idx": i, "x0": x0, "x1": x1, "w_pt": w_pt, "w_mm": w_mm})

    if len(raw_cols) < 4:
        min_x, max_x = grid_x[0], grid_x[-1]
        step = (max_x - min_x) / 4.0
        raw_cols = [
            {"col_idx": i, "x0": min_x + i * step, "x1": min_x + (i + 1) * step,
             "w_pt": step, "w_mm": step / _PT_PER_MM}
            for i in range(4)
        ]

    # ── 1. Extract Complete Flat Dieline Net (All Panels & All Flaps) ───────
    all_dieline_panels = []
    all_columns_info = []

    for i, col in enumerate(raw_cols):
        x0, x1 = col["x0"], col["x1"]
        td = [d["rect"].y0 for d in session.dieline_drawings
              if d["rect"].y1 <= y_top_hinge + 3 and not (d["rect"].x1 < x0 or d["rect"].x0 > x1)]
        bd = [d["rect"].y1 for d in session.dieline_drawings
              if d["rect"].y0 >= y_bot_hinge - 3 and not (d["rect"].x1 < x0 or d["rect"].x0 > x1)]

        min_ty = min(td) if td else y_top_hinge
        max_by = max(bd) if bd else y_bot_hinge
        top_h_mm = max(0.0, (y_top_hinge - min_ty) / _PT_PER_MM)
        bot_h_mm = max(0.0, (max_by - y_bot_hinge) / _PT_PER_MM)
        col_w_mm = round(col["w_mm"], 1)
        body_h_mm = round((y_bot_hinge - y_top_hinge) / _PT_PER_MM, 1)

        col_dict = {
            "col_index": i,
            "panel_number": i + 1,
            "x0": x0,
            "x1": x1,
            "w_mm": col_w_mm,
            "h_mm": body_h_mm,
            "top_flap_h_mm": round(top_h_mm, 1),
            "bot_flap_h_mm": round(bot_h_mm, 1),
            "top_y": min_ty,
            "bot_y": max_by,
        }
        all_columns_info.append(col_dict)

        # A. Body panel
        all_dieline_panels.append({
            "name": f"Flat_Col{i+1}_Body",
            "type": "body",
            "col_idx": i,
            "rect": (x0, y_top_hinge, x1, y_bot_hinge),
            "w_mm": col_w_mm,
            "h_mm": body_h_mm,
        })
        # B. Top flap (if height > 5mm)
        if top_h_mm > 5.0:
            all_dieline_panels.append({
                "name": f"Flat_Col{i+1}_TopFlap",
                "type": "top_flap",
                "col_idx": i,
                "rect": (x0, min_ty, x1, y_top_hinge),
                "w_mm": col_w_mm,
                "h_mm": round(top_h_mm, 1),
            })
        # C. Bottom flap (if height > 5mm)
        if bot_h_mm > 5.0:
            all_dieline_panels.append({
                "name": f"Flat_Col{i+1}_BotFlap",
                "type": "bot_flap",
                "col_idx": i,
                "rect": (x0, y_bot_hinge, x1, max_by),
                "w_mm": col_w_mm,
                "h_mm": round(bot_h_mm, 1),
            })

    session.all_columns_info = all_columns_info
    session.all_dieline_panels = all_dieline_panels
    print(f"[Step 3] Extracted {len(all_dieline_panels)} total flat dieline panels across {len(all_columns_info)} columns.")

    # ── 2. Select 4 Active Body Panels for the 3D Box ─────────────────────
    if len(all_columns_info) > 4:
        # Determine which column to ignore
        ignored_idx = session.ignored_col_idx
        if ignored_idx is None:
            # Deterministic geometric heuristic:
            # Test excluding far-left (idx 0) vs excluding far-right (idx -1)
            # Evaluate which remaining 4 columns have closer opposing face width matching
            # Set A: ignore 0 -> [1, 2, 3, 4]
            diff_A = abs(all_columns_info[1]["w_mm"] - all_columns_info[3]["w_mm"]) + \
                     abs(all_columns_info[2]["w_mm"] - all_columns_info[4]["w_mm"])
            # Set B: ignore 4 -> [0, 1, 2, 3]
            diff_B = abs(all_columns_info[0]["w_mm"] - all_columns_info[2]["w_mm"]) + \
                     abs(all_columns_info[1]["w_mm"] - all_columns_info[3]["w_mm"])

            # Also check if col 0 has shorter flaps or is an asymmetrical tuck tab
            if all_columns_info[0]["top_flap_h_mm"] < all_columns_info[1]["top_flap_h_mm"] * 0.7:
                ignored_idx = 0
            elif diff_A <= diff_B:
                ignored_idx = 0
            else:
                ignored_idx = len(all_columns_info) - 1

        session.ignored_col_idx = ignored_idx
        active_body = [c for idx, c in enumerate(all_columns_info) if idx != ignored_idx][:4]
        print(f"[Step 3] Multi-column package ({len(all_columns_info)} cols). Ignored column: Panel {ignored_idx + 1}. Active 3D walls: {[c['panel_number'] for c in active_body]}")
    else:
        session.ignored_col_idx = None
        active_body = all_columns_info[:4]

    session.detected_body_panels = active_body

    # ── 3. Determine Front Face ───────────────────────────────────────────
    if front_idx is None:
        if session.front_panel_idx is not None and 0 <= session.front_panel_idx < 4:
            front_idx = session.front_panel_idx
        else:
            candidates = []
            for i, p in enumerate(active_body):
                candidates.append((p.get("w_mm", 0.0), p.get("top_flap_h_mm", 0.0), i))
            candidates.sort(key=lambda c: (-c[0], -c[1]))
            front_idx = candidates[0][2]

    front_idx = max(0, min(3, int(front_idx)))
    session.front_panel_idx = front_idx

    # Assign 4 perimeter walls around the box
    is_up_down = getattr(session, "is_upside_down", False)
    if is_up_down:
        F = active_body[front_idx]
        L = active_body[(front_idx + 1) % 4]
        B = active_body[(front_idx + 2) % 4]
        R = active_body[(front_idx + 3) % 4]
    else:
        F = active_body[front_idx]
        R = active_body[(front_idx + 1) % 4]
        B = active_body[(front_idx + 2) % 4]
        L = active_body[(front_idx + 3) % 4]

    # ── 4. Calculate Exact 3D Dimensions ──────────────────────────────────
    W_mm = F["w_mm"]
    D_mm = L["w_mm"]
    H_mm = (y_bot_hinge - y_top_hinge) / _PT_PER_MM

    session.box_dims_mm = {
        "W": round(W_mm, 1),
        "D": round(D_mm, 1),
        "H": round(H_mm, 1),
    }

    # ── 5. Auto-detect or use User-specified Lid Panels ───────────────────
    top_lid_idx = session.top_lid_panel_idx
    bot_lid_idx = session.bot_lid_panel_idx

    if top_lid_idx is None or bot_lid_idx is None:
        auto_top, auto_bot = _auto_detect_lid_panels(session, active_body, y_top_hinge, y_bot_hinge)
        if top_lid_idx is None:
            top_lid_idx = auto_top
        if bot_lid_idx is None:
            bot_lid_idx = auto_bot

    top_lid_idx = max(0, min(3, int(top_lid_idx)))
    bot_lid_idx = max(0, min(3, int(bot_lid_idx)))
    session.top_lid_panel_idx = top_lid_idx
    session.bot_lid_panel_idx = bot_lid_idx

    p_top = active_body[top_lid_idx]
    p_bot = active_body[bot_lid_idx]

    top_depth_mm = D_mm if abs(p_top["w_mm"] - W_mm) < abs(p_top["w_mm"] - D_mm) else W_mm
    top_lid_h_pt = top_depth_mm * _PT_PER_MM

    bot_depth_mm = D_mm if abs(p_bot["w_mm"] - W_mm) < abs(p_bot["w_mm"] - D_mm) else W_mm
    bot_lid_h_pt = bot_depth_mm * _PT_PER_MM

    panels: dict[str, tuple] = {}
    if is_up_down:
        panels["front"] = (F["x0"], y_top_hinge, F["x1"], y_bot_hinge)
        panels["right"] = (R["x0"], y_top_hinge, R["x1"], y_bot_hinge)
        panels["back"]  = (B["x0"], y_top_hinge, B["x1"], y_bot_hinge)
        panels["left"]  = (L["x0"], y_top_hinge, L["x1"], y_bot_hinge)
        panels["top"]    = (p_top["x0"], y_bot_hinge, p_top["x1"], y_bot_hinge + top_lid_h_pt)
        panels["bottom"] = (p_bot["x0"], y_top_hinge - bot_lid_h_pt, p_bot["x1"], y_top_hinge)
    else:
        panels["front"] = (F["x0"], y_top_hinge, F["x1"], y_bot_hinge)
        panels["right"] = (R["x0"], y_top_hinge, R["x1"], y_bot_hinge)
        panels["back"]  = (B["x0"], y_top_hinge, B["x1"], y_bot_hinge)
        panels["left"]  = (L["x0"], y_top_hinge, L["x1"], y_bot_hinge)
        panels["top"]    = (p_top["x0"], y_top_hinge - top_lid_h_pt, p_top["x1"], y_top_hinge)
        panels["bottom"] = (p_bot["x0"], y_bot_hinge, p_bot["x1"], y_bot_hinge + bot_lid_h_pt)

    session.parsed_panels = panels

    if top_lid_idx == bot_lid_idx:
        session.box_type_name = "Straight Tuck End / Folding Carton"
        session.box_type_key = "STE"
    elif abs(top_lid_idx - bot_lid_idx) == 2:
        session.box_type_name = "Reverse Tuck End (RTE)"
        session.box_type_key = "RTE"
    else:
        session.box_type_name = "Folding Carton with Tuck Lids"
        session.box_type_key = "RTE"

    print(f"[Step 3] Front=Panel {active_body[front_idx]['panel_number']} | Box Dims: W={session.box_dims_mm['W']} D={session.box_dims_mm['D']} H={session.box_dims_mm['H']} mm ({session.box_type_name})")

    _compute_panel_uvs(session)
    return panels


def _compute_panel_uvs(session: AppSession) -> None:
    """Convert parsed panel bounds (PDF points) → normalised UV (u_min,v_min,u_max,v_max)."""
    t = session.transform
    if not t:
        return

    M = t.get("M_affine")
    W_tex = t.get("W_tex", 1)
    H_tex = t.get("H_tex", 1)

    def pt2uv(x: float, y: float) -> tuple[float, float]:
        if M is not None:
            px = M[0][0] * x + M[0][1] * y + M[0][2]
            py = M[1][0] * x + M[1][1] * y + M[1][2]
        else:
            px = x * t.get("scale_x", 1.0) + t.get("offset_x", 0.0)
            py = y * t.get("scale_y", 1.0) + t.get("offset_y", 0.0)
        u = float(px / W_tex)
        v = float(1.0 - (py / H_tex))
        return u, v

    panel_uvs: dict[str, tuple] = {}
    for face, (x0, y0, x1, y1) in session.parsed_panels.items():
        u0, v0 = pt2uv(x0, y0)
        u1, v1 = pt2uv(x1, y1)
        u_min = max(0.0, min(1.0, min(u0, u1)))
        u_max = max(0.0, min(1.0, max(u0, u1)))
        v_min = max(0.0, min(1.0, min(v0, v1)))
        v_max = max(0.0, min(1.0, max(v0, v1)))
        panel_uvs[face] = (u_min, v_min, u_max, v_max)

    session.panel_uvs = panel_uvs
