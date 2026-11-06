"""
Standard folding carton box-type definitions.
Each BoxTypeDef encodes the panel column roles and row structure
used by panel_parser to map dieline geometry to 3D faces.
"""
from dataclasses import dataclass, field


@dataclass
class BoxTypeDef:
    key: str            # short identifier, e.g. "RTE"
    name: str           # display name
    description: str
    # Ordered list of panel roles from LEFT to RIGHT across the dieline net.
    # Valid tokens: "glue" (glue flap), "F" (front), "B" (back), "L" (left side), "R" (right side)
    col_roles: list     # e.g. ["glue", "L", "F", "R", "B"]
    front_col_idx: int  # index in col_roles where "F" appears
    top_flap_is_tuck: bool = True
    bot_flap_is_tuck: bool = True
    has_glue_flap: bool = True
    # SVG/PNG diagram filename inside resources/box_diagrams/ (informational only)
    diagram: str = ""


BOX_TYPES: dict[str, BoxTypeDef] = {
    "RTE": BoxTypeDef(
        key="RTE",
        name="Reverse Tuck End",
        description=(
            "Most common retail carton. Top tuck tongue opens from the front panel; "
            "bottom tuck tongue opens from the back panel."
        ),
        col_roles=["glue", "L", "F", "R", "B"],
        front_col_idx=2,
        top_flap_is_tuck=True,
        bot_flap_is_tuck=True,
        has_glue_flap=True,
        diagram="rte.png",
    ),
    "STE": BoxTypeDef(
        key="STE",
        name="Straight Tuck End",
        description=(
            "Both top and bottom tuck tongues open from the same side (front panel). "
            "Common in cosmetics and pharmaceuticals."
        ),
        col_roles=["glue", "L", "F", "R", "B"],
        front_col_idx=2,
        top_flap_is_tuck=True,
        bot_flap_is_tuck=True,
        has_glue_flap=True,
        diagram="ste.png",
    ),
    "AUTO": BoxTypeDef(
        key="AUTO",
        name="Auto Bottom / Crash Lock",
        description=(
            "Standard tuck top; bottom has a pre-glued auto-locking base that pops "
            "open automatically. Used for heavy products."
        ),
        col_roles=["glue", "L", "F", "R", "B"],
        front_col_idx=2,
        top_flap_is_tuck=True,
        bot_flap_is_tuck=False,
        has_glue_flap=True,
        diagram="auto.png",
    ),
    "CSSC": BoxTypeDef(
        key="CSSC",
        name="CSSC (Corner-Stitch Seal & Cut)",
        description=(
            "Tray-style carton assembled with corner stitches. No tuck tongues. "
            "Common for food, confectionery, and display trays."
        ),
        col_roles=["L", "F", "R", "B"],
        front_col_idx=1,
        top_flap_is_tuck=False,
        bot_flap_is_tuck=False,
        has_glue_flap=False,
        diagram="cssc.png",
    ),
    "TRAY": BoxTypeDef(
        key="TRAY",
        name="Tray + Lid (2-piece)",
        description=(
            "Open-top tray with a separate telescope lid. Both nets usually appear "
            "on the same PDF sheet."
        ),
        col_roles=["L", "F", "R", "B"],
        front_col_idx=1,
        top_flap_is_tuck=False,
        bot_flap_is_tuck=False,
        has_glue_flap=False,
        diagram="tray.png",
    ),
    "SLEEVE": BoxTypeDef(
        key="SLEEVE",
        name="Sleeve",
        description=(
            "Simple tubular sleeve that slides over an inner tray or product. "
            "No top or bottom flaps, just a wraparound body with a glue seam."
        ),
        col_roles=["glue", "L", "F", "R", "B"],
        front_col_idx=2,
        top_flap_is_tuck=False,
        bot_flap_is_tuck=False,
        has_glue_flap=True,
        diagram="sleeve.png",
    ),
}
