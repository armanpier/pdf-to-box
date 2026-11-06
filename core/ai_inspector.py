"""
Local Vision AI Inspector (Bionic / LM Studio / Ollama compatible).
Inspects aligned panel crops, dieline columns, and full textures to determine:
  1. Texture canonical orientation (0, 90, 180, 270 degrees).
  2. Multi-column disambiguation: which column to ignore if >4 columns (extra glue flap).
  3. Which panel is the FRONT face (main logo/hero title).
  4. Whether the artwork on the body panels is upside down (180 deg).
  5. Which flaps are the TOP and BOTTOM lids and whether their UVs need flipping.
"""
import base64
import json
import urllib.request
import cv2
import numpy as np
from .session import AppSession
from .ai_status import check_bionic_status, check_ollama_status


def _encode_image_b64(img_bgr: np.ndarray, max_dim: int = 1024) -> str:
    h, w = img_bgr.shape[:2]
    if max(h, w) > max_dim:
        scale = max_dim / float(max(h, w))
        img_bgr = cv2.resize(img_bgr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", img_bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
    if not ok:
        return ""
    return base64.b64encode(buf.tobytes()).decode("utf-8")


def _query_local_vlm(prompt: str, img_b64: str = "") -> dict | None:
    """
    Queries local AI endpoints:
      1. Ollama (http://127.0.0.1:11434/v1/chat/completions) - supports vision & text
      2. Bionic / LM Studio (http://127.0.0.1:1234/v1/chat/completions)
    """
    endpoints = [
        ("http://127.0.0.1:11434/v1/chat/completions", "qwen2.5vl:7b"),
        ("http://127.0.0.1:11434/v1/chat/completions", "qwen2.5vl:latest"),
        ("http://127.0.0.1:1234/v1/chat/completions", "qwen3.5-9b-the-defiant-fable-uncensored-heretic-neo-imatrix-max-mtp"),
        ("http://127.0.0.1:1234/v1/chat/completions", "local-model"),
    ]

    for url, model_name in endpoints:
        msg_content = []
        if prompt:
            msg_content.append({"type": "text", "text": prompt})
        if img_b64:
            msg_content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}})

        # Fallback to simple string content if no image
        messages_payload = [
            {"role": "user", "content": msg_content if img_b64 else prompt}
        ]

        payload = {
            "model": model_name,
            "temperature": 0.0,
            "max_tokens": 800,
            "messages": messages_payload,
        }
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                choice = data["choices"][0]["message"]
                content = choice.get("content") or choice.get("reasoning_content") or ""
                # Strip markdown fences if present
                content = content.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
                # Find first { and last }
                start = content.find("{")
                end = content.rfind("}")
                if start != -1 and end != -1 and end > start:
                    return json.loads(content[start:end+1])
        except Exception:
            continue
    return None


def ai_estimate_texture_orientation_and_bounds(img_bgr: np.ndarray) -> dict:
    """
    Queries local VLM to identify orientation (0, 90, 180, 270) and rough bounding box of artwork.
    """
    img_b64 = _encode_image_b64(img_bgr, max_dim=800)
    if not img_b64:
        return {"rotation_deg": 0, "bbox": [0.0, 0.0, 1.0, 1.0]}

    prompt = (
        "Analyze this packaging diffuse texture image.\n"
        "1. Identify the clockwise rotation in degrees (0, 90, 180, or 270) needed to make the main packaging brand text upright and readable.\n"
        "2. Identify the bounding box of the package artwork net inside the image as normalized coordinates [ymin, xmin, ymax, xmax] between 0.0 and 1.0.\n"
        "Return ONLY JSON: {\"rotation_deg\": int, \"bbox\": [ymin, xmin, ymax, xmax]}"
    )

    res = _query_local_vlm(prompt, img_b64)
    if res and isinstance(res, dict):
        rot = int(res.get("rotation_deg", res.get("rotation", 0)))
        if rot not in (0, 90, 180, 270):
            rot = 0
        bbox = res.get("bbox", [0.0, 0.0, 1.0, 1.0])
        if not isinstance(bbox, list) or len(bbox) != 4:
            bbox = [0.0, 0.0, 1.0, 1.0]
        return {"rotation_deg": rot, "bbox": [float(v) for v in bbox]}

    return {"rotation_deg": 0, "bbox": [0.0, 0.0, 1.0, 1.0]}


def ai_decide_multi_column_selection(session: AppSession) -> dict:
    """
    When a dieline net contains >4 columns (e.g. 5 columns where one is an extra glue/sleeve tab),
    queries Bionic or Ollama to decide which column should be ignored for the 3D box body,
    and which column is the Hero Front panel.
    """
    cols = session.all_columns_info
    if len(cols) <= 4:
        return {"ignored_col_idx": None, "front_panel_number": None}

    cols_summary = []
    for c in cols:
        cols_summary.append({
            "panel_number": c["panel_number"],
            "col_index": c["col_index"],
            "width_mm": c["w_mm"],
            "top_flap_h_mm": c["top_flap_h_mm"],
            "bot_flap_h_mm": c["bot_flap_h_mm"],
        })

    prompt = (
        f"You are a packaging CAD engineer analyzing a folding box dieline net.\n"
        f"The dieline has {len(cols)} columns from left to right:\n"
        f"{json.dumps(cols_summary, indent=2)}\n\n"
        f"A 3D rectangular box requires exactly 4 perimeter walls (Front, Back, Left, Right).\n"
        f"One of the outer columns (far-left index 0, or far-right index {len(cols)-1}) is an extra glue/sleeve flap\n"
        f"that should be IGNORED for folding the 3D box body.\n"
        f"Determine:\n"
        f"1. 'ignore_col_idx': Which column index (0 for Panel 1, or {len(cols)-1} for Panel {len(cols)}) should be IGNORED for the 3D box body?\n"
        f"2. 'front_panel_number': Which Panel Number (1 to {len(cols)}) is the primary FRONT (Hero brand) panel?\n"
        f"3. 'reasoning': Brief explanation.\n"
        f"Return ONLY JSON: {{\"ignore_col_idx\": int, \"front_panel_number\": int, \"reasoning\": str}}"
    )

    res = _query_local_vlm(prompt)
    if res and isinstance(res, dict) and "ignore_col_idx" in res:
        print(f"[AI Inspector] Multi-column decision from AI: {res}")
        return res

    # Fallback to geometric heuristic:
    # Set A: ignore 0 -> [1, 2, 3, 4]
    diff_A = abs(cols[1]["w_mm"] - cols[3]["w_mm"]) + abs(cols[2]["w_mm"] - cols[4]["w_mm"])
    # Set B: ignore 4 -> [0, 1, 2, 3]
    diff_B = abs(cols[0]["w_mm"] - cols[2]["w_mm"]) + abs(cols[1]["w_mm"] - cols[3]["w_mm"])

    chosen_ignore = 0 if diff_A <= diff_B else len(cols) - 1
    return {
        "ignore_col_idx": chosen_ignore,
        "front_panel_number": 4 if chosen_ignore == 0 else 3,
        "reasoning": "Selected column with smaller opposite-face width variance and asymmetrical flap height."
    }


def ai_verify_alignment_and_panels(session: AppSession, annotated_preview_bgr: np.ndarray) -> dict:
    """
    Sends the numbered panel preview to the local VLM so it can identify the Front panel,
    upside-down state, and lid orientations.
    """
    img_b64 = _encode_image_b64(annotated_preview_bgr)
    if not img_b64:
        return {}

    num_panels = len(session.detected_body_panels) or 4
    prompt = (
        f"You are an expert packaging pre-press engineer. Look at this packaging dieline texture "
        f"with body columns numbered 1 to {num_panels} from left to right.\n"
        f"Determine:\n"
        f"1. 'front_panel_idx': Which column index (0 to {num_panels-1}) contains the primary FRONT brand logo/hero design?\n"
        f"2. 'is_upside_down': Is the text/logo on the main body panels upside-down (rotated 180 degrees)? (true/false)\n"
        f"3. 'top_lid_panel_idx': Which column index has the main top closing lid flap above the upper fold line?\n"
        f"4. 'bot_lid_panel_idx': Which column index has the main bottom closing lid flap below the lower fold line?\n"
        f"Return ONLY valid JSON: "
        f"{{\"front_panel_idx\": int, \"is_upside_down\": bool, \"top_lid_panel_idx\": int, \"bot_lid_panel_idx\": int}}"
    )

    res = _query_local_vlm(prompt, img_b64)
    if res and isinstance(res, dict):
        print(f"[AI Inspector] Local AI analysis: {res}")
        if "front_panel_idx" in res and res["front_panel_idx"] in range(num_panels):
            session.front_panel_idx = int(res["front_panel_idx"])
        if "is_upside_down" in res:
            session.is_upside_down = bool(res["is_upside_down"])
        if "top_lid_panel_idx" in res and res["top_lid_panel_idx"] in range(num_panels):
            session.top_lid_panel_idx = int(res["top_lid_panel_idx"])
        if "bot_lid_panel_idx" in res and res["bot_lid_panel_idx"] in range(num_panels):
            session.bot_lid_panel_idx = int(res["bot_lid_panel_idx"])
    else:
        print("[AI Inspector] No local AI responder detected on :1234 or :11434 — using geometric heuristics.")
    return res or {}
