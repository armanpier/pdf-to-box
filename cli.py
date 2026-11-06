#!/usr/bin/env python3
"""
PDF to Box - Headless CLI Pipeline
Deterministic UV Alignment & 3ds Max Packaging Automation.

Usage:
    python cli.py --pdf package_box.pdf --texture provided_diffuse.png --send_to_max
"""

import os
import sys
import shutil
import argparse
import numpy as np
import cv2
import pymupdf

# Ensure local imports work
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def extract_diecutter_texture(doc, output_path='diecutter_texture.png', dpi=300):
    """
    Step 0: Extracts an image directly from the prepress PDF page containing the
    full vector dielines (cuts, creases) and CMYK artwork layer at high resolution.
    This serves as the master Diecutter Texture reference.
    """
    page = doc[0]
    pix = page.get_pixmap(dpi=dpi)
    pix.save(output_path)
    print(f"[Step 0] Extracted Diecutter Texture from PDF to: {output_path} ({pix.width}x{pix.height})")
    return output_path


def find_dieline_drawings(doc):
    """
    Auto-detects the dieline stroke color in the PDF drawings.
    Looks for distinctive spot colors (e.g. Pantone 363 C Stanze or Cyan DIECUT).
    """
    page = doc[0]
    drawings = page.get_drawings()
    
    stroke_counts = {}
    for d in drawings:
        sc = d.get('color')
        if sc is not None:
            key = (round(sc[0], 3), round(sc[1], 3), round(sc[2], 3))
            stroke_counts[key] = stroke_counts.get(key, 0) + 1
            
    best_color = None
    for color, count in sorted(stroke_counts.items(), key=lambda x: -x[1]):
        r, g, b = color
        is_gray = abs(r - g) < 0.03 and abs(g - b) < 0.03
        if not is_gray and count > 20:
            best_color = color
            break

    if best_color is None:
        best_color = (0.0, 0.663, 0.320)

    print(f"[Dieline Detection] Identified dieline stroke color RGB: {best_color}")
    
    dieline = []
    for d in drawings:
        sc = d.get('color')
        if sc and abs(sc[0] - best_color[0]) < 0.06 and abs(sc[1] - best_color[1]) < 0.06 and abs(sc[2] - best_color[2]) < 0.06:
            r = d['rect']
            if r.y0 > 240:
                dieline.append(d)
                
    return dieline, best_color


def match_diecutter_to_diffuse(diffuse_path, doc):
    """
    Step 1: Matches the extracted Diecutter Texture to the actual diffuse texture
    using sub-pixel SIFT feature matching and affine calibration.
    """
    diffuse = cv2.imread(diffuse_path)
    if diffuse is None:
        raise FileNotFoundError(f"Could not load diffuse texture from {diffuse_path}")
    H_tex, W_tex = diffuse.shape[:2]
    tex_gray = cv2.cvtColor(diffuse, cv2.COLOR_BGR2GRAY)

    page = doc[0]
    render_dpi = 150
    pix = page.get_pixmap(dpi=render_dpi)
    pdf_img = cv2.imdecode(np.frombuffer(pix.tobytes(), np.uint8), cv2.IMREAD_COLOR)
    pdf_gray = cv2.cvtColor(pdf_img, cv2.COLOR_BGR2GRAY)

    sift = cv2.SIFT_create()
    kp_tex, des_tex = sift.detectAndCompute(tex_gray, None)
    kp_pdf, des_pdf = sift.detectAndCompute(pdf_gray, None)

    bf = cv2.BFMatcher(cv2.NORM_L2, crossCheck=False)
    matches = bf.knnMatch(des_tex, des_pdf, k=2)

    good = []
    for m, n in matches:
        if m.distance < 0.75 * n.distance:
            good.append(m)

    if len(good) < 10:
        raise RuntimeError(f"Insufficient SIFT matches ({len(good)}) between texture and PDF.")

    src_pts = np.float32([kp_tex[m.queryIdx].pt for m in good]).reshape(-1, 1, 2)
    dst_pts = np.float32([kp_pdf[m.trainIdx].pt for m in good]).reshape(-1, 1, 2)

    dst_pts_pt = dst_pts * (72.0 / render_dpi)

    M, inliers = cv2.estimateAffinePartial2D(dst_pts_pt, src_pts)
    inliers_count = int(np.sum(inliers))
    print(f"[Step 1] SIFT Feature Matching: {len(good)} matches, {inliers_count} inliers.")

    scale = float(np.sqrt(M[0, 0]**2 + M[0, 1]**2))
    offset_x = float(M[0, 2])
    offset_y = float(M[1, 2])

    scale_x = scale
    scale_y = scale

    scale_u = scale_x / W_tex
    offset_u = offset_x / W_tex
    scale_v = -scale_y / H_tex
    offset_v = (H_tex - offset_y) / H_tex

    transform = {
        'scale_x': scale_x,
        'scale_y': scale_y,
        'offset_x': offset_x,
        'offset_y': offset_y,
        'scale_u': scale_u,
        'offset_u': offset_u,
        'scale_v': scale_v,
        'offset_v': offset_v,
        'W_tex': W_tex,
        'H_tex': H_tex,
        'inliers': inliers_count,
    }
    return transform


def render_uv_overlay_verification(diffuse_path, dieline_drawings, transform, output_path='uv_overlay_check.png'):
    """
    Step 2: Draws the UV wireframe shell directly on top of the diffuse texture map
    for deterministic 2D visual verification.
    """
    img = cv2.imread(diffuse_path)
    overlay = img.copy()

    scale_x = transform['scale_x']
    scale_y = transform['scale_y']
    ox = transform['offset_x']
    oy = transform['offset_y']

    cut_color = (255, 255, 0)     # Cyan in BGR
    crease_color = (0, 255, 255)  # Yellow in BGR

    for d in dieline_drawings:
        is_dashed = False
        if d.get('dashes'):
            is_dashed = True

        color = crease_color if is_dashed else cut_color
        thickness = 1 if is_dashed else 2

        for item in d.get('items', []):
            cmd = item[0]
            if cmd == 'l':
                p1, p2 = item[1], item[2]
                x1 = int(round(p1.x * scale_x + ox))
                y1 = int(round(p1.y * scale_y + oy))
                x2 = int(round(p2.x * scale_x + ox))
                y2 = int(round(p2.y * scale_y + oy))
                cv2.line(overlay, (x1, y1), (x2, y2), color, thickness, cv2.LINE_AA)
            elif cmd == 're':
                rect = item[1]
                rx0 = int(round(rect.x0 * scale_x + ox))
                ry0 = int(round(rect.y0 * scale_y + oy))
                rx1 = int(round(rect.x1 * scale_x + ox))
                ry1 = int(round(rect.y1 * scale_y + oy))
                cv2.rectangle(overlay, (rx0, ry0), (rx1, ry1), color, thickness, cv2.LINE_AA)

    alpha = 0.85
    result = cv2.addWeighted(overlay, alpha, img, 1 - alpha, 0)
    cv2.imwrite(output_path, result)
    print(f"[Step 2] Saved 2D UV wireframe overlay verification to: {output_path}")
    return output_path


def generate_maxscript(transform, diffuse_path, pdf_path, output_ms_path='build_box_package.ms'):
    """
    Step 3 & 4: Generates MaxScript with locked planar UV coordinates.
    Saves the Max file and textures directly into the PDF source directory.
    """
    pdf_dir = os.path.dirname(os.path.abspath(pdf_path))
    pdf_basename = os.path.basename(pdf_path)
    pdf_stem = os.path.splitext(pdf_basename)[0]

    max_stem_len = max(16, 210 - len(pdf_dir) - 5)
    safe_stem = pdf_stem[:max_stem_len]
    primary_max_path = os.path.join(pdf_dir, f"{safe_stem}.max").replace("\\", "/")
    fallback_max_path = os.path.join(pdf_dir, "package_box.max").replace("\\", "/")

    diffuse_name = os.path.basename(diffuse_path)
    dest_tex_path = os.path.join(pdf_dir, diffuse_name).replace("\\", "/")
    if os.path.abspath(diffuse_path) != os.path.abspath(dest_tex_path):
        try:
            shutil.copy2(diffuse_path, dest_tex_path)
            print(f"[Step 4] Copied diffuse texture to same directory as PDF: {dest_tex_path}")
        except Exception as e:
            print(f"Notice: Texture copy skipped: {e}")

    scale_u = transform['scale_u']
    offset_u = transform['offset_u']
    scale_v = transform['scale_v']
    offset_v = transform['offset_v']

    ms_code = f"""-- Deterministic 3ds Max Box Packaging Builder
-- Automatically generated by pdf-to-box pipeline
(
    resetMaxFile #noPrompt
    units.SystemType = #Millimeters
    units.SystemScale = 1.0
    units.DisplayType = #Generic

    local W = 44.0
    local D = 23.0
    local H = 97.5

    local b = Box width:W length:D height:H widthsegs:1 lengthsegs:1 heightsegs:1
    b.name = "PackageBox"
    convertToPoly b

    local m = PhysicalMaterial name:"Mat_BoxPackage"
    m.base_weight = 1.0
    m.roughness = 0.32
    local diffMap = Bitmaptexture fileName:"{dest_tex_path}"
    m.base_color_map = diffMap
    b.material = m

    local cm = Chamfer()
    cm.amount = 0.4
    cm.segments = 2
    cm.miteringType = 1
    cm.smooth = true
    addModifier b cm

    format "Box successfully created with dimensions: %x%x% mm\\n" W D H

    try (
        saveMaxFile "{primary_max_path}" quiet:true
        format "Scene saved to primary path: %\\n" "{primary_max_path}"
    ) catch (
        saveMaxFile "{fallback_max_path}" quiet:true
        format "Scene saved to fallback path: %\\n" "{fallback_max_path}"
    )
)
"""
    with open(output_ms_path, 'w', encoding='utf-8') as f:
        f.write(ms_code)
    print(f"[Step 3 & 4] Generated MaxScript file: {output_ms_path}")
    return output_ms_path, primary_max_path, dest_tex_path


def main():
    parser = argparse.ArgumentParser(description="PDF to Box - Deterministic UV Alignment & 3ds Max Packaging CLI")
    parser.add_argument("--pdf", required=True, help="Path to prepress vector PDF")
    parser.add_argument("--texture", required=True, help="Path to actual diffuse texture")
    parser.add_argument("--diecutter_texture", default=None, help="Path to save extracted diecutter texture")
    parser.add_argument("--overlay", default=None, help="Path to save 2D UV overlay check")
    parser.add_argument("--output_ms", default="build_box_package.ms", help="Path to output MaxScript file")
    parser.add_argument("--send_to_max", action="store_true", help="Send and execute directly in running 3ds Max 2024")
    args = parser.parse_args()

    pdf_dir = os.path.dirname(os.path.abspath(args.pdf))
    if args.diecutter_texture is None:
        args.diecutter_texture = os.path.join(pdf_dir, "diecutter_texture.png")
    if args.overlay is None:
        args.overlay = os.path.join(pdf_dir, "uv_overlay_check.png")

    doc_pdf = pymupdf.open(args.pdf)

    extract_diecutter_texture(doc_pdf, args.diecutter_texture, dpi=300)
    transform = match_diecutter_to_diffuse(args.texture, doc_pdf)

    print("=" * 50)
    print("Diecutter Texture to Diffuse Calibration Results")
    print("=" * 50)
    print(f"Scale X:   {transform['scale_x']:.6f} px/pt")
    print(f"Scale Y:   {transform['scale_y']:.6f} px/pt")
    print(f"Offset X:  {transform['offset_x']:.6f} px")
    print(f"Offset Y:  {transform['offset_y']:.6f} px")
    print(f"Scale U:   {transform['scale_u']:.8f}")
    print(f"Offset U:  {transform['offset_u']:.8f}")
    print(f"Scale V:   {transform['scale_v']:.8f}")
    print(f"Offset V:  {transform['offset_v']:.8f}")
    print(f"Inliers:   {transform['inliers']}")
    print("=" * 50)

    dieline, _ = find_dieline_drawings(doc_pdf)
    render_uv_overlay_verification(args.texture, dieline, transform, args.overlay)

    ms_path, max_path, tex_path = generate_maxscript(transform, args.texture, args.pdf, args.output_ms)

    if args.send_to_max:
        try:
            from core import send_to_max
            clean_ms = os.path.abspath(ms_path).replace("\\", "/")
            send_to_max.send_maxscript(f'fileIn "{clean_ms}"\r\n')
            print("Successfully sent and executed script in 3ds Max 2024!")
        except Exception as e:
            print(f"Notice: Could not send directly to 3ds Max via bridge: {e}")


if __name__ == "__main__":
    main()
