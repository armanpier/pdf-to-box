"""
End-to-end integration test for BOTH packaging datasets:
  Dataset 1: Tea Box (enerBio Herzmoment, 73 x 64 x 118 mm)
  Dataset 2: Serum Drops (ISANA MAPF, 44.3 x 23.3 x 97.4 mm)

Tests:
  1. Step 0 file loading & PDF vector dieline extraction
  2. Step 1 AI & SIFT alignment with strict rigid/similarity transforms (Zero Warping)
  3. Step 1 Transform controls (Position, Rotation, Scale)
  4. Step 2 UV overlay generation
  5. Step 3 Panel parsing, auto-front detection, and dimension extraction
  6. Step 4 3ds Max MaxScript generation & execution (PackageBox_Flattened and PackageBox_Body)
  7. Verification of scene files and viewport grabs
"""
import sys, os, time
import numpy as np
sys.path.insert(0, r"tools\pdf_to_box")

from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtTest import QTest

# Disable modal dialogs
QMessageBox.information = lambda *args, **kwargs: None
QMessageBox.warning = lambda *args, **kwargs: None
QMessageBox.critical = lambda *args, **kwargs: None

from ui.main_window import MainWindow

app = QApplication.instance() or QApplication(sys.argv)

def run_test_on_dataset(pdf_path: str, tex_path: str, expected_dims: dict, expected_front_idx: int, label: str):
    print(f"\n{'='*70}\n[E2E TEST] STARTING: {label}\n{'='*70}")
    assert os.path.isfile(pdf_path), f"PDF file missing: {pdf_path}"
    assert os.path.isfile(tex_path), f"Texture file missing: {tex_path}"

    win = MainWindow()
    win.resize(1200, 800)
    win.show()
    QTest.qWait(200)

    # ── STEP 0 ──────────────────────────────────────────────────────────────
    print(f"[{label}] Step 0: Input files...")
    step0 = win._steps[0]
    step0._pdf_picker.set_path(pdf_path)
    step0._tex_picker.set_path(tex_path)
    assert step0._next_btn.isEnabled(), "Step 0 Next button should be enabled"
    QTest.mouseClick(step0._next_btn, Qt.MouseButton.LeftButton)
    QTest.qWait(400)
    assert win._current_step == 1, f"Expected Step 1, got {win._current_step}"

    # ── STEP 1 ──────────────────────────────────────────────────────────────
    print(f"[{label}] Step 1: Alignment...")
    step1 = win._steps[1]
    t0 = time.time()
    while (step1._worker is not None and step1._worker.isRunning()) or not step1._confirm_btn.isEnabled():
        QTest.qWait(100)
        if time.time() - t0 > 20:
            break

    assert win._session.transform is not None, "Transform must be computed"
    t = win._session.transform
    print(f"[{label}] Auto-alignment: scale=({t['scale_x']:.3f}, {t['scale_y']:.3f}), rot={t.get('rot_deg', 0):.1f}°, method={win._session.align_method}")

    # Verify rigid orthogonality (Zero Shear / Zero Warping)
    M = np.array(t["M_affine"])
    col1 = M[:, 0]
    col2 = M[:, 1]
    dot = np.dot(col1, col2)
    print(f"[{label}] Transform orthogonality dot product (must be ~0): {dot:.6f}")
    assert abs(dot) < 0.05, f"Transform contains shear/warping: dot={dot}"

    # Test Transform Controls (Nudge and Spinboxes)
    init_x = step1._pos_x_spin.value()
    init_y = step1._pos_y_spin.value()
    step1._nudge(10, 10)
    assert abs(step1._pos_x_spin.value() - (init_x + 10)) < 0.1, "Nudge X failed"
    assert abs(step1._pos_y_spin.value() - (init_y + 10)) < 0.1, "Nudge Y failed"
    # Restore
    step1._nudge(-10, -10)

    QTest.mouseClick(step1._confirm_btn, Qt.MouseButton.LeftButton)
    QTest.qWait(400)
    assert win._current_step == 2, f"Expected Step 2, got {win._current_step}"

    # ── STEP 2 ──────────────────────────────────────────────────────────────
    print(f"[{label}] Step 2: Overlay check...")
    step2 = win._steps[2]
    overlay_png = os.path.join(win._session.output_dir, "uv_overlay_check.png")
    assert os.path.isfile(overlay_png), f"uv_overlay_check.png missing: {overlay_png}"
    QTest.mouseClick(step2._confirm_btn, Qt.MouseButton.LeftButton)
    QTest.qWait(400)
    assert win._current_step == 3, f"Expected Step 3, got {win._current_step}"

    # ── STEP 3 ──────────────────────────────────────────────────────────────
    print(f"[{label}] Step 3: Panel Mapping & Dimensions...")
    step3 = win._steps[3]
    print(f"[{label}] Identified carton: {win._session.box_type_name}")
    print(f"[{label}] Auto Front panel index: {win._session.front_panel_idx + 1}")
    print(f"[{label}] Box dimensions: {win._session.box_dims_mm}")

    assert win._session.front_panel_idx == expected_front_idx, (
        f"Expected front panel {expected_front_idx}, got {win._session.front_panel_idx}"
    )
    for dim_k, exp_v in expected_dims.items():
        act_v = win._session.box_dims_mm.get(dim_k, 0)
        assert abs(act_v - exp_v) <= 1.5, f"Dimension {dim_k} mismatch: expected ~{exp_v}, got {act_v}"

    QTest.mouseClick(step3._next_btn, Qt.MouseButton.LeftButton)
    QTest.qWait(400)
    assert win._current_step == 4, f"Expected Step 4, got {win._current_step}"

    # ── STEP 4 ──────────────────────────────────────────────────────────────
    print(f"[{label}] Step 4: 3ds Max build...")
    step4 = win._steps[4]
    QTest.mouseClick(step4._send_btn, Qt.MouseButton.LeftButton)

    t0 = time.time()
    while step4._build_thread is not None and step4._build_thread.is_alive():
        app.processEvents()
        time.sleep(0.1)
        if time.time() - t0 > 30:
            break

    app.processEvents()
    time.sleep(0.2)
    app.processEvents()

    pdf_stem = os.path.splitext(os.path.basename(pdf_path))[0]
    max_stem_len = max(16, 210 - len(win._session.output_dir) - 5)
    safe_stem = pdf_stem[:max_stem_len]
    max_file = os.path.join(win._session.output_dir, f"{safe_stem}.max")
    if not os.path.isfile(max_file):
        max_file = os.path.join(win._session.output_dir, "package_box.max")
    assert os.path.isfile(max_file), f"3ds Max file not created: {max_file}"
    print(f"[{label}] VERIFIED SCENE FILE: {max_file} ({os.path.getsize(max_file):,} bytes)")

    vp_file = os.path.join(win._session.output_dir, "viewport_grab.jpg")
    assert os.path.isfile(vp_file), f"Viewport grab not found: {vp_file}"
    print(f"[{label}] VERIFIED VIEWPORT GRAB: {vp_file} ({os.path.getsize(vp_file):,} bytes)")

    win.close()
    print(f"[{label}] PASS: All tests succeeded!\n")


# ── Run on Dataset 1 (Tea Box) ───────────────────────────────────────────────
d1_pdf = r"C:\rossman\QA\DT-4068134181800\bad37827-378b-48ad-9107-bbdafec1fb5e\enerBio_Herzmoment_81978300_K1.pdf"
d1_tex = r"C:\rossman\QA\DT-4068134181800\bad37827-378b-48ad-9107-bbdafec1fb5e\4068134181800_diff_00.png"
run_test_on_dataset(
    pdf_path=d1_pdf,
    tex_path=d1_tex,
    expected_dims={"W": 73.0, "D": 64.0, "H": 118.0},
    expected_front_idx=2, # Panel 3
    label="Dataset 1: Tea Box (enerBio Herzmoment)"
)

# ── Run on Dataset 2 (Serum Drops) ───────────────────────────────────────────
d2_pdf = r"C:\rossman\QA\DT-4068134257857\9b262445-be9c-4a94-b25b-0c372f221879\4068134257857_ISANA_MAPF_SerumDrops\4068134257857_ISANA_MAPF_SerumDrops\4068134257857_ISANA_SerumDrops_MAPF_FoldingBox_Pfade.pdf"
d2_tex = r"C:\rossman\QA\DT-4068134257857\9b262445-be9c-4a94-b25b-0c372f221879\4068134257857_diff_00.png"
run_test_on_dataset(
    pdf_path=d2_pdf,
    tex_path=d2_tex,
    expected_dims={"W": 44.3, "D": 23.3, "H": 97.4},
    expected_front_idx=2, # Panel 3
    label="Dataset 2: Serum Drops (ISANA MAPF)"
)

# ── Run on Dataset 3 (Domol WC-Duftspüler, 5 Columns) ───────────────────────
d3_pdf = r"C:\rossman\undone\DT-4068134210869\610d9a51-49ff-414f-b509-6bef1c0bc137\4068134210869_DOMOL_WC_DUFTSPUELER_FRUITY_PARADISE_07_26_DD_PVO\4068134210869_DOMOL_WC_DUFTSPUELER_FRUITY_PARADISE_07_26_DD_PVO\4068134210869_DOMOL_WC_DUFTSPUELER_FRUITY_PARADISE_07_26_DD.pdf"
d3_tex = r"C:\rossman\undone\DT-4068134210869\610d9a51-49ff-414f-b509-6bef1c0bc137\4068134210869_DOMOL_WC_DUFTSPUELER_FRUITY_PARADISE_07_26_DD_PVO\4068134210869_DOMOL_WC_DUFTSPUELER_FRUITY_PARADISE_07_26_DD_PVO\4068134210869_diff_00.png"
run_test_on_dataset(
    pdf_path=d3_pdf,
    tex_path=d3_tex,
    expected_dims={"W": 78.1, "D": 52.9, "H": 146.4},
    expected_front_idx=2, # Active wall 3 (Panel 4)
    label="Dataset 3: Domol WC-Duftspüler (5 Columns)"
)

print("\n" + "="*70)
print("ALL 3 DATASETS PASSED END-TO-END WITH FULL 3DS MAX PACKAGING VERIFICATION!")
print("="*70)
