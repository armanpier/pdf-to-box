"""
Step 4 – Generate Autodesk 3ds Max 2024 MaxScript from session data.
Builds both:
  1. PackageBox_Flattened: 2D planar panels representing 100% of all dieline net
     panels and flaps lying on the ground plane in XY space with cardstock thickness.
  2. PackageBox_Body: 3D folded carton constructed from 6 UV-locked planes welded
     into a watertight box with Chamfer.
"""
import os
import shutil
from .session import AppSession


def _compute_face_mapverts(face: str, u_min: float, v_min: float,
                           u_max: float, v_max: float, session: AppSession) -> list[tuple[float, float]]:
    """
    Returns the 4 MapVert UV tuples [mv1, mv2, mv3, mv4] corresponding to:
    mv1 = BL, mv2 = BR, mv3 = TL, mv4 = TR.
    """
    is_up_down = getattr(session, "is_upside_down", False)
    flip_top = getattr(session, "flip_top_lid_180", False)
    flip_bot = getattr(session, "flip_bot_lid_180", False)

    if face in ("front", "back", "left", "right"):
        if is_up_down:
            return [(u_max, v_max), (u_min, v_max), (u_max, v_min), (u_min, v_min)]
        else:
            return [(u_min, v_min), (u_max, v_min), (u_min, v_max), (u_max, v_max)]

    elif face == "top":
        mvs = [(u_min, v_max), (u_max, v_max), (u_min, v_min), (u_max, v_min)]
        if flip_top or is_up_down:
            mvs = [mvs[3], mvs[2], mvs[1], mvs[0]]
        return mvs

    elif face == "bottom":
        mvs = [(u_min, v_min), (u_max, v_min), (u_min, v_max), (u_max, v_max)]
        if flip_bot or is_up_down:
            mvs = [mvs[3], mvs[2], mvs[1], mvs[0]]
        return mvs

    return [(u_min, v_min), (u_max, v_min), (u_min, v_max), (u_max, v_max)]


def generate_maxscript(session: AppSession, output_path: str | None = None) -> str:
    """
    Generate the MaxScript file from session data.
    Builds both:
      1. PackageBox_Flattened (flat unfolded dieline mesh with ALL panels and flaps)
      2. PackageBox_Body (folded 3D box assembled from 6 UV-locked planes welded into a watertight box)
    Returns the path to the saved .ms file.
    """
    if output_path is None:
        output_path = os.path.join(session.output_dir, "build_box_package.ms")

    dims = session.box_dims_mm
    W = dims.get("W", 64.0)
    D = dims.get("D", 73.0)
    H = dims.get("H", 118.0)

    pdf_dir = session.output_dir
    pdf_stem = os.path.splitext(os.path.basename(session.pdf_path))[0]
    # Ensure total .max file path stays under 3ds Max temporary save buffer limit (210 chars)
    max_stem_len = max(16, 210 - len(pdf_dir) - 5)
    safe_stem = pdf_stem[:max_stem_len]

    tex_filename = os.path.basename(session.texture_path)
    dest_tex_path = os.path.join(pdf_dir, tex_filename)
    if os.path.abspath(session.texture_path) != os.path.abspath(dest_tex_path):
        shutil.copyfile(session.texture_path, dest_tex_path)

    clean_tex_path  = os.path.abspath(dest_tex_path).replace("\\", "/")
    primary_max     = os.path.abspath(os.path.join(pdf_dir, f"{safe_stem}.max")).replace("\\", "/")
    alias_max       = os.path.abspath(os.path.join(pdf_dir, "package_box.max")).replace("\\", "/")
    viewport_grab   = os.path.abspath(os.path.join(pdf_dir, "viewport_grab.jpg")).replace("\\", "/")
    log_path        = os.path.abspath(os.path.join(pdf_dir, "build_status.txt")).replace("\\", "/")

    pt_to_mm = 25.4 / 72.0
    t = session.transform
    M = t.get("M_affine") if t else None
    W_tex = t.get("W_tex", 1) if t else 1
    H_tex = t.get("H_tex", 1) if t else 1

    def to_uv_local(x_pt: float, y_pt: float) -> tuple[float, float]:
        if M is not None:
            px = M[0][0] * x_pt + M[0][1] * y_pt + M[0][2]
            py = M[1][0] * x_pt + M[1][1] * y_pt + M[1][2]
            return float(px / W_tex), float(1.0 - (py / H_tex))
        elif t:
            px = x_pt * t.get("scale_x", 1.0) + t.get("offset_x", 0.0)
            py = y_pt * t.get("scale_y", 1.0) + t.get("offset_y", 0.0)
            return float(px / W_tex), float(1.0 - (py / H_tex))
        return 0.0, 0.0

    # 1. Build Flattened Dieline Net with ALL panels and flaps
    flat_panels_ms = ""
    panels_to_build = session.all_dieline_panels if getattr(session, "all_dieline_panels", None) else [
        {"name": f"Flat_{k}", "rect": v} for k, v in session.parsed_panels.items()
    ]

    for idx, p_info in enumerate(panels_to_build):
        p_name = p_info["name"]
        x0, y0, x1, y1 = p_info["rect"]
        pw_mm = abs(x1 - x0) * pt_to_mm
        ph_mm = abs(y1 - y0) * pt_to_mm
        if pw_mm < 0.5 or ph_mm < 0.5:
            continue

        cx_mm = ((x0 + x1) * 0.5) * pt_to_mm
        cy_mm = (session.pdf_height_pt - (y0 + y1) * 0.5) * pt_to_mm

        mv1 = to_uv_local(x0, y1)
        mv2 = to_uv_local(x1, y1)
        mv3 = to_uv_local(x0, y0)
        mv4 = to_uv_local(x1, y0)

        flat_panels_ms += f"""
    p_flat_{idx} = Plane length:{ph_mm:.3f} width:{pw_mm:.3f} lengthsegs:1 widthsegs:1 mapcoords:on name:"{p_name}"
    p_flat_{idx}.pos = [{cx_mm:.3f}, {cy_mm:.3f}, 0]
    convertToPoly p_flat_{idx}
    polyop.setNumMapVerts p_flat_{idx} 1 4 keep:false
    polyop.setMapVert p_flat_{idx} 1 1 [{mv1[0]:.6f}, {mv1[1]:.6f}, 0]
    polyop.setMapVert p_flat_{idx} 1 2 [{mv2[0]:.6f}, {mv2[1]:.6f}, 0]
    polyop.setMapVert p_flat_{idx} 1 3 [{mv3[0]:.6f}, {mv3[1]:.6f}, 0]
    polyop.setMapVert p_flat_{idx} 1 4 [{mv4[0]:.6f}, {mv4[1]:.6f}, 0]
    polyop.setMapFace p_flat_{idx} 1 1 #(3, 1, 2, 4)
    p_flat_{idx}.material = mat
"""

    # 2. Build 6 3D Folded Planes with explicit non-shared UVs
    face_planes_def = [
        ("p_front", "P_Front", W, H, "front",  "-90 0 0",     f"[0, -{D*0.5:.3f}, {H*0.5:.3f}]"),
        ("p_back",  "P_Back",  W, H, "back",   "90 0 180",    f"[0, {D*0.5:.3f}, {H*0.5:.3f}]"),
        ("p_right", "P_Right", D, H, "right",  "0 -90 -90",   f"[{W*0.5:.3f}, 0, {H*0.5:.3f}]"),
        ("p_left",  "P_Left",  D, H, "left",   "0 90 90",     f"[-{W*0.5:.3f}, 0, {H*0.5:.3f}]"),
        ("p_top",   "P_Top",   W, D, "top",    "0 0 0",       f"[0, 0, {H:.3f}]"),
        ("p_bot",   "P_Bot",   W, D, "bottom", "180 0 0",     f"[0, 0, 0]"),
    ]

    folded_planes_ms = ""
    for var_name, obj_name, pw, ph, face_key, rot_euler, pos_vec in face_planes_def:
        if face_key in session.panel_uvs:
            u_min, v_min, u_max, v_max = session.panel_uvs[face_key]
        else:
            u_min, v_min, u_max, v_max = 0.0, 0.0, 1.0, 1.0
        mvs = _compute_face_mapverts(face_key, u_min, v_min, u_max, v_max, session)

        folded_planes_ms += f"""
    {var_name} = Plane length:{ph:.3f} width:{pw:.3f} lengthsegs:1 widthsegs:1 mapcoords:on name:"{obj_name}"
    convertToPoly {var_name}
    polyop.setNumMapVerts {var_name} 1 4 keep:false
    polyop.setMapVert {var_name} 1 1 [{mvs[0][0]:.6f}, {mvs[0][1]:.6f}, 0]
    polyop.setMapVert {var_name} 1 2 [{mvs[1][0]:.6f}, {mvs[1][1]:.6f}, 0]
    polyop.setMapVert {var_name} 1 3 [{mvs[2][0]:.6f}, {mvs[2][1]:.6f}, 0]
    polyop.setMapVert {var_name} 1 4 [{mvs[3][0]:.6f}, {mvs[3][1]:.6f}, 0]
    polyop.setMapFace {var_name} 1 1 #(3, 1, 2, 4)
    {var_name}.rotation = (eulerAngles {rot_euler})
    {var_name}.pos = {pos_vec}
"""

    ms_code = f"""-- ============================================================
-- PDF-to-Box Package Builder – Auto-generated MaxScript
-- Box type : {session.box_type_key} ({session.box_type_name})
-- Dims     : W={W} mm  D={D} mm  H={H} mm
-- Texture  : {clean_tex_path}
-- ============================================================

try (
    resetMaxFile #noPrompt
    delete objects

    units.SystemType  = #Millimeters
    units.SystemScale = 1.0
    units.DisplayType = #Metric
    units.MetricType  = #Millimeters

    -- 1. Coated cardstock PhysicalMaterial
    mat             = PhysicalMaterial name:"M_PackageBox"
    mat.roughness   = 0.32
    mat.base_weight = 1.0

    tex_diff              = Bitmaptexture fileName:@"{clean_tex_path}"
    mat.base_color_map    = tex_diff
    showTextureMap mat true

    -- 2. Build Flattened Dieline Package Net (Complete Set of All Panels & Flaps)
{flat_panels_ms}
    flat_objs = for o in objects where (matchPattern o.name pattern:"Flat_*") collect o
    if flat_objs.count > 0 do (
        flat_root = flat_objs[1]
        flat_root.name = "PackageBox_Flattened"
        for i = 2 to flat_objs.count do polyop.attach flat_root flat_objs[i]
        sh = Shell innerAmount:0.0 outerAmount:0.35
        addModifier flat_root sh
        CenterPivot flat_root
        flat_root.pos = [- ({W * 2.5 + 50.0:.1f}), 0, 0]
    )

    -- 3. Build Folded 3D Box Body
{folded_planes_ms}

    -- 4. Attach 3D planes into a watertight box with discrete UVs
    box_body = p_front
    box_body.name = "PackageBox_Body"
    polyop.attach box_body p_back
    polyop.attach box_body p_right
    polyop.attach box_body p_left
    polyop.attach box_body p_top
    polyop.attach box_body p_bot

    -- Weld coincident spatial vertices (0.5 mm threshold)
    vw = Vertex_Weld threshold:0.5
    addModifier box_body vw
    maxOps.CollapseNodeTo box_body 1 true

    -- Assign cardstock material and smoothing
    box_body.material = mat
    for f = 1 to (polyop.getNumFaces box_body) do (
        polyop.setFaceSmoothGroup box_body f 1
    )

    -- Cardstock edge chamfer
    ch = Chamfer amount:0.4 segments:2
    addModifier box_body ch

    -- 5. Lighting & Camera Setup
    sun = Directionallight name:"KeyLight" rgb:(color 255 250 240) multiplier:1.2
    sun.pos = [{W * 2.0:.1f}, -{D * 3.0:.1f}, {H * 2.5:.1f}]
    sun.target = Targetobject pos:[0, 0, {H * 0.5:.1f}]

    fill = Directionallight name:"FillLight" rgb:(color 220 235 255) multiplier:0.6
    fill.pos = [-{W * 2.5:.1f}, {D * 2.0:.1f}, {H * 1.5:.1f}]
    fill.target = Targetobject pos:[0, 0, {H * 0.5:.1f}]

    -- 6. Save Scenes
    saveMaxFile @\"{primary_max}\" clearNeedSaveFlag:true useNewFile:true quiet:true
    saveMaxFile @\"{alias_max}\" clearNeedSaveFlag:true useNewFile:false quiet:true

    -- 7. High-Res Viewport Grab
    viewport.setLayout #layout_1
    viewport.setType #view_persp_user
    max zoomext sel all
    try (
        vp_setting = NitrousGraphicsManager.GetActiveViewportSetting()
        if vp_setting != undefined do vp_setting.VisualStyleMode = #Shaded
    ) catch ()
    completeRedraw()
    sleep 0.5

    dib = gw.getViewportDib()
    if dib != undefined do (
        dib.filename = @\"{viewport_grab}\"
        save dib
    )

    -- Log Success
    f = openFile @\"{log_path}\" mode:\"w\"
    format \"SUCCESS: Box built -> %\\n\" @\"{primary_max}\" to:f
    close f

) catch (
    err = getCurrentException()
    f = openFile @\"{log_path}\" mode:\"w\"
    format \"ERROR: %\\n\" err to:f
    close f
)
"""
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(ms_code)

    session.ms_path = output_path
    print(f"[Step 4] MaxScript saved: {output_path} (Flat net: {len(panels_to_build)} panels/flaps)")
    return output_path
