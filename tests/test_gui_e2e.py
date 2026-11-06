import sys, os, time
sys.path.insert(0, r"tools\pdf_to_box")

from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QMouseEvent
from PyQt6.QtTest import QTest

# Disable modal blocking dialogs
QMessageBox.information = lambda *args, **kwargs: None
QMessageBox.warning = lambda *args, **kwargs: None
QMessageBox.critical = lambda *args, **kwargs: None

from ui.main_window import MainWindow

print("=== STARTING FULL GUI E2E TEST ===")
app = QApplication.instance() or QApplication(sys.argv)

win = MainWindow()
win.resize(1200, 800)
win.show()
QTest.qWait(200)

pdf_path = r"C:\rossman\QA\DT-4068134181800\bad37827-378b-48ad-9107-bbdafec1fb5e\enerBio_Herzmoment_81978300_K1.pdf"
tex_path = r"C:\rossman\QA\DT-4068134181800\bad37827-378b-48ad-9107-bbdafec1fb5e\4068134181800_diff_00.png"

# --- STEP 0: Input files ---
print("\n[E2E] Step 0: Setting input paths...")
step0 = win._steps[0]
step0._pdf_picker.set_path(pdf_path)
step0._tex_picker.set_path(tex_path)
assert step0._next_btn.isEnabled(), "Step 0 Next button should be enabled"
QTest.mouseClick(step0._next_btn, Qt.MouseButton.LeftButton)
QTest.qWait(500)

print(f"[E2E] Current step index: {win._current_step}")
assert win._current_step == 1, f"Expected step index 1, got {win._current_step}"

# --- STEP 1: Alignment ---
print("\n[E2E] Step 1: Checking alignment...")
step1 = win._steps[1]
t0 = time.time()
while (step1._worker is not None and step1._worker.isRunning()) or not step1._confirm_btn.isEnabled():
    QTest.qWait(100)
    if time.time() - t0 > 15:
        break
assert win._session.transform is not None, "Transform must be computed"
print(f"Alignment scale: ({win._session.transform['scale_x']:.2f}, {win._session.transform['scale_y']:.2f})")
QTest.mouseClick(step1._confirm_btn, Qt.MouseButton.LeftButton)
QTest.qWait(500)

assert win._current_step == 2, f"Expected step index 2, got {win._current_step}"

# --- STEP 2: UV Overlay Check ---
print("\n[E2E] Step 2: Overlay check...")
step2 = win._steps[2]
overlay_png = os.path.join(win._session.output_dir, "uv_overlay_check.png")
assert os.path.isfile(overlay_png), "uv_overlay_check.png was not generated"
print(f"Overlay check image verified: {overlay_png}")
QTest.mouseClick(step2._confirm_btn, Qt.MouseButton.LeftButton)
QTest.qWait(500)

assert win._current_step == 3, f"Expected step index 3, got {win._current_step}"

# --- STEP 3: Visual Face Mapping ---
print("\n[E2E] Step 3: Interactive Face Mapping...")
step3 = win._steps[3]
assert len(step3._canvas._panel_items) == 6, f"Expected 6 overlay rects, got {len(step3._canvas._panel_items)}"
print(f"Detected 3D box: {win._session.box_type_name}")
print(f"Dimensions: {win._session.box_dims_mm}")
print(f"Initial Front Panel: {win._session.front_panel_idx + 1}")

# Test clicking Panel 1 on the canvas
p1_item = [it for it in step3._canvas._panel_items if it.panel_idx == 0][0]
p1_vp = step3._canvas.mapFromScene(p1_item.rect().center())
ev = QMouseEvent(QMouseEvent.Type.MouseButtonPress, QPointF(p1_vp), Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
step3._canvas.mousePressEvent(ev)
QTest.qWait(200)

print(f"After canvas click on Panel 1 -> Front panel: {win._session.front_panel_idx + 1}")
assert win._session.front_panel_idx == 0, "Canvas click should have set Front to Panel 1 (idx 0)"
assert step3._radio_buttons[0].isChecked(), "Radio button 1 should be checked"

# Switch to Panel 3 (the tea box hero front "enerBio Herzmoment")
step3._radio_buttons[2].setChecked(True)
QTest.qWait(200)
print(f"Set via Radio Button to Panel 3 -> Front panel: {win._session.front_panel_idx + 1}")
assert win._session.front_panel_idx == 2, "Expected front panel 2 (Panel 3)"

# Test Settings & Orientation controls
print("\n[E2E] Testing Orientation & Flap Settings controls...")
assert hasattr(step3, "_upside_down_chk"), "Step 3 must have upside-down checkbox"
assert hasattr(step3, "_top_lid_combo"), "Step 3 must have top lid combobox"
assert hasattr(step3, "_bot_lid_combo"), "Step 3 must have bot lid combobox"

# Test toggling upside-down checkbox
step3._upside_down_chk.setChecked(True)
QTest.qWait(200)
assert win._session.is_upside_down is True, "Session is_upside_down should be True"
print("Verified: Upside-down checkbox toggled to True -> Session updated")

step3._upside_down_chk.setChecked(False)
QTest.qWait(200)
assert win._session.is_upside_down is False, "Session is_upside_down should be False"
print("Verified: Upside-down checkbox toggled to False -> Session updated")

# Set Top lid to Panel 2 (the back panel with the top closing lid) and flip 180°
step3._top_lid_combo.setCurrentIndex(2) # Panel 2
step3._flip_top_chk.setChecked(True)
QTest.qWait(100)
assert win._session.top_lid_panel_idx == 1, "Session top_lid_panel_idx should be 1 (Panel 2)"
assert win._session.flip_top_lid_180 is True, "flip_top_lid_180 should be True"
print(f"Verified: Top lid set to Panel {win._session.top_lid_panel_idx + 1} (Flipped 180°)")

QTest.mouseClick(step3._next_btn, Qt.MouseButton.LeftButton)
QTest.qWait(500)
assert win._current_step == 4, f"Expected step index 4, got {win._current_step}"

# --- STEP 4: Build & Send to 3ds Max ---
print("\n[E2E] Step 4: Building packaging in 3ds Max...")
step4 = win._steps[4]
QTest.mouseClick(step4._send_btn, Qt.MouseButton.LeftButton)

print("Waiting for 3ds Max execution...")
t0 = time.time()
while step4._build_thread is not None and step4._build_thread.is_alive():
    app.processEvents()
    time.sleep(0.1)
    if time.time() - t0 > 30:
        break

# Process queued completion events
app.processEvents()
time.sleep(0.2)
app.processEvents()

print(f"3ds Max finished build in {time.time() - t0:.2f}s")

# Verify final assets
pdf_stem = os.path.splitext(os.path.basename(pdf_path))[0]
max_file = os.path.join(win._session.output_dir, f"{pdf_stem}.max")
assert os.path.isfile(max_file), f"3ds Max scene file not found: {max_file}"
assert os.path.getsize(max_file) > 100000, f"3ds Max file too small: {os.path.getsize(max_file)}"
print(f"VERIFIED ASSET: {max_file} ({os.path.getsize(max_file):,} bytes)")

viewport_file = os.path.join(win._session.output_dir, "viewport_grab.jpg")
assert os.path.isfile(viewport_file), f"Viewport grab file not found: {viewport_file}"
print(f"VERIFIED ASSET: {viewport_file} ({os.path.getsize(viewport_file):,} bytes)")

status_file = os.path.join(win._session.output_dir, "build_status.txt")
assert os.path.isfile(status_file), f"Status file not found: {status_file}"
with open(status_file) as f:
    st = f.read().strip()
print(f"VERIFIED STATUS: {st}")
assert "SUCCESS" in st

# Verify that viewport preview label in GUI has pixmap loaded
assert step4._preview_lbl.pixmap() is not None, "Step 4 UI viewport preview should have a pixmap loaded!"
print(f"VERIFIED GUI: Viewport preview is loaded in Step 4 UI with size: {step4._preview_lbl.pixmap().size()}")

print("\n=======================================================")
print("=== COMPLETE END-TO-END GUI TEST PASSED WITH 100% SUCCESS ===")
print("=======================================================")
