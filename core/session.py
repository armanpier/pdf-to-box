"""
Shared application state passed between all pipeline steps.
"""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AppSession:
    # ── Inputs ─────────────────────────────────────────────────────────────
    pdf_path: str = ""
    texture_path: str = ""
    output_dir: str = ""          # resolved to same folder as PDF at step 0

    # ── Step 0: PDF extraction results ─────────────────────────────────────
    pdf_doc: Any = None           # pymupdf.Document (not serialisable)
    pdf_width_pt: float = 0.0     # page width in PDF points (1 pt = 1/72 in)
    pdf_height_pt: float = 0.0
    diecutter_texture_path: str = ""
    dieline_drawings: list = field(default_factory=list)
    dieline_color: tuple = (0.0, 0.663, 0.320)  # auto-detected RGB

    # ── Step 1: Texture alignment results ──────────────────────────────────
    transform: dict = field(default_factory=dict)
    # Keys present in transform:
    #   scale_x, scale_y  – px per PDF-point
    #   offset_x, offset_y – pixel offset of PDF origin onto texture
    #   scale_u, offset_u  – normalized UV equivalents (X axis)
    #   scale_v, offset_v  – normalized UV equivalents (Y axis, flipped)
    #   W_tex, H_tex       – texture pixel dimensions
    #   inliers            – confidence count (SIFT) or 99 (crop) or 4 (manual)
    align_method: str = "crop"    # "crop" | "sift" | "manual"
    align_quality: float = 0.0    # 0.0–1.0

    # ── Step 2: UV overlay ─────────────────────────────────────────────────
    overlay_path: str = ""

    # ── Step 3: Box type & panel parsing ───────────────────────────────────
    box_type_key: str = "RTE"
    box_type_name: str = "Standard Folding Carton"
    front_panel_idx: Any = None                        # 0-based index among active body panels (0..3), None for auto
    top_lid_panel_idx: Any = None                      # None for auto, or 0..3
    bot_lid_panel_idx: Any = None                      # None for auto, or 0..3
    ignored_col_idx: Any = None                        # Column index excluded from 3D box body if >4 columns (None for auto)
    is_upside_down: bool = False                       # True if box/texture is upside down (flip 180°)
    flip_top_lid_180: bool = False                     # True if top lid UVs should be rotated 180°
    flip_bot_lid_180: bool = False                     # True if bottom lid UVs should be rotated 180°
    all_columns_info: list = field(default_factory=list)      # All detected columns (4, 5, or more)
    all_dieline_panels: list = field(default_factory=list)    # Complete set of all body panels + flaps in flat net
    detected_body_panels: list = field(default_factory=list)  # Active 4 panels used for the 3D box body
    box_dims_mm: dict = field(default_factory=dict)    # {"W": 0, "H": 0, "D": 0}
    parsed_panels: dict = field(default_factory=dict)  # face → (x0,y0,x1,y1) pt
    panel_uvs: dict = field(default_factory=dict)      # face → (u_min,v_min,u_max,v_max)
    grid_x: list = field(default_factory=list)         # sorted column splits (pt)
    grid_y: list = field(default_factory=list)         # sorted row splits (pt)

    # ── Step 4: Output ─────────────────────────────────────────────────────
    ms_path: str = ""
    max_path: str = ""

    def step_done(self, step: int) -> bool:
        return {
            0: bool(self.pdf_path and self.texture_path),
            1: bool(self.diecutter_texture_path and self.dieline_drawings),
            2: bool(self.transform),
            3: bool(self.overlay_path),
            4: bool(self.panel_uvs),
            5: bool(self.ms_path),
        }.get(step, False)
