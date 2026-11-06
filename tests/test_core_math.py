"""
Unit tests for core affine math, coordinate transformations, and non-white bounds detection.
These tests run fast and independently without GUI or external PDF dependencies.
"""
import numpy as np
import pytest
from core.session import AppSession
from core.texture_aligner import _find_nonwhite_bounds, _build_transform
from core.manual_aligner import get_transform_params


def test_find_nonwhite_bounds_synthetic():
    # Create 100x100 white canvas
    img = np.full((100, 100, 3), 255, dtype=np.uint8)
    # Paint a dark rectangle from x=20..79, y=30..69
    img[30:70, 20:80] = 50

    x0, y0, x1, y1 = _find_nonwhite_bounds(img, threshold=240)
    assert x0 == 20
    assert y0 == 30
    assert x1 == 80
    assert y1 == 70


def test_build_transform_math():
    # Texture 1000x1000, scale 2.0, offset 100, 200
    W_tex, H_tex = 1000, 1000
    scale_x, scale_y = 2.0, 2.0
    offset_x, offset_y = 100.0, 200.0

    t = _build_transform(scale_x, scale_y, offset_x, offset_y, W_tex, H_tex)

    assert pytest.approx(t["scale_u"]) == 2.0 / 1000.0
    assert pytest.approx(t["offset_u"]) == 100.0 / 1000.0
    assert pytest.approx(t["scale_v"]) == -2.0 / 1000.0
    # offset_v = (1000 - 200) / 1000 = 0.8
    assert pytest.approx(t["offset_v"]) == 0.8


def test_manual_aligner_params():
    W_tex, H_tex = 2000, 2000
    scale_x, scale_y = 1.5, 1.5
    offset_x, offset_y = 50.0, 75.0

    t = _build_transform(scale_x, scale_y, offset_x, offset_y, W_tex, H_tex, rot_deg=0.0, pos_x=500.0, pos_y=500.0)
    session = AppSession()
    params = get_transform_params(t, session)

    assert pytest.approx(params["scale_x"]) == 1.5
    assert pytest.approx(params["scale_y"]) == 1.5
    assert pytest.approx(params["rot_deg"]) == 0.0
    assert pytest.approx(params["pos_x"]) == 500.0
    assert pytest.approx(params["pos_y"]) == 500.0
