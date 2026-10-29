import numpy as np
import pytest
from PIL import Image

from app.overlays import (
    ACCENT_ORANGE,
    apply_overlay_to_frames,
    create_overlay_layer,
    draw_caption_overlay,
    get_font,
)


def test_get_font_returns_usable_font():
    font = get_font(34)
    assert font is not None
    bbox = font.getbbox("Sample Text")
    assert bbox[2] > bbox[0]
    assert bbox[3] > bbox[1]


def test_overlay_contrast_on_pure_white_image():
    # Pure white background to test contrast requirement
    white_img = Image.new("RGB", (1280, 720), color=(255, 255, 255))
    caption = "Luxury Penthouse Suite\nPrime Downtown Location"

    composited = draw_caption_overlay(white_img, caption, scene_type="title")
    assert composited.size == (1280, 720)
    assert composited.mode == "RGB"

    arr = np.array(composited)

    # 1. Top of image should remain pure white
    top_pixels = arr[100, 640]
    assert np.all(top_pixels >= 250)

    # 2. Bottom bar region should have darkened pixels (semi-transparent dark bar)
    bar_pixels = arr[680, 50]  # bottom left of the bar away from text
    # R, G, B should be significantly darker than 255
    assert np.all(bar_pixels < 100), f"Bar background should be dark for contrast, got {bar_pixels}"

    # 3. Orange accent line must be present at the top edge of the bar
    # Search for orange pixels in the lower 200 rows
    lower_crop = arr[520:720, :]
    # Orange is high red (~255), medium green (~106), low blue (~26)
    orange_mask = (
        (lower_crop[:, :, 0] > 200)
        & (lower_crop[:, :, 1] > 80)
        & (lower_crop[:, :, 1] < 150)
        & (lower_crop[:, :, 2] < 60)
    )
    assert np.sum(orange_mask) > 1000, "Orange accent line must be visible and rendered"


def test_overlay_on_pure_black_image():
    black_img = Image.new("RGB", (1280, 720), color=(0, 0, 0))
    caption = "✦ Panoramic Creek View"

    composited = draw_caption_overlay(black_img, caption, scene_type="feature")
    assert composited.size == (1280, 720)

    arr = np.array(composited)
    # White text should be present
    white_mask = (arr[:, :, 0] > 200) & (arr[:, :, 1] > 200) & (arr[:, :, 2] > 200)
    assert np.sum(white_mask) > 100, "Text should be drawn in white"


def test_all_scene_types_rendering():
    base = Image.new("RGB", (1280, 720), color=(50, 50, 50))

    scenes_to_test = [
        ("title", "Azure Crest Residences\nPalm Beach Road, Navi Mumbai"),
        ("feature", "✦ Infinity Rooftop Pool\nElevated living experience"),
        ("details", "Apartment • ₹1.85 Crore\n3 BHK • 1,420 sq ft"),
        ("cta", "Call +91 98200 12345 or visit azurecrest.in"),
    ]

    for stype, caption in scenes_to_test:
        out = draw_caption_overlay(base, caption, scene_type=stype)
        assert out.size == (1280, 720)


def test_apply_overlay_to_frames_batch():
    frames = [Image.new("RGB", (1280, 720), color=(i * 10, i * 10, i * 10)) for i in range(12)]
    caption = "Spacious Living Room"

    overlaid = apply_overlay_to_frames(frames, caption, scene_type="feature")
    assert len(overlaid) == 12
    for frame in overlaid:
        assert frame.size == (1280, 720)
