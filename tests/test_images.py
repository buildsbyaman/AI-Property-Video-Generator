import io
import numpy as np
import pytest
from PIL import Image

from app.images import (
    TARGET_HEIGHT,
    TARGET_WIDTH,
    cover_crop,
    frames_to_numpy,
    generate_ken_burns_frames,
    open_and_normalize_image,
)


def test_cover_crop_aspect_ratios():
    # 1. Square image (1000x1000)
    img_square = Image.new("RGB", (1000, 1000), color="red")
    cropped_square = cover_crop(img_square)
    assert cropped_square.size == (TARGET_WIDTH, TARGET_HEIGHT)

    # 2. Ultra-wide image (2560x1000)
    img_wide = Image.new("RGB", (2560, 1000), color="blue")
    cropped_wide = cover_crop(img_wide)
    assert cropped_wide.size == (TARGET_WIDTH, TARGET_HEIGHT)

    # 3. Portrait image (800x1600)
    img_portrait = Image.new("RGB", (800, 1600), color="green")
    cropped_portrait = cover_crop(img_portrait)
    assert cropped_portrait.size == (TARGET_WIDTH, TARGET_HEIGHT)

    # 4. Standard Full HD (1920x1080)
    img_fhd = Image.new("RGB", (1920, 1080), color="purple")
    cropped_fhd = cover_crop(img_fhd)
    assert cropped_fhd.size == (TARGET_WIDTH, TARGET_HEIGHT)


def test_open_and_normalize_image_modes():
    # Valid JPEG
    buf_jpg = io.BytesIO()
    Image.new("RGB", (640, 480), color="yellow").save(buf_jpg, format="JPEG")
    res_jpg = open_and_normalize_image(buf_jpg.getvalue())
    assert res_jpg is not None
    assert res_jpg.mode == "RGB"

    # RGBA with transparency
    buf_png = io.BytesIO()
    Image.new("RGBA", (640, 480), color=(255, 0, 0, 128)).save(buf_png, format="PNG")
    res_png = open_and_normalize_image(buf_png.getvalue())
    assert res_png is not None
    assert res_png.mode == "RGB"

    # Corrupt data
    corrupt_data = b"PK\x03\x04not_an_image"
    res_corrupt = open_and_normalize_image(corrupt_data)
    assert res_corrupt is None


def test_ken_burns_frames_generation():
    # Create test image with contrasting pattern so zoom produces measurable pixel difference
    img = Image.new("RGB", (1280, 720), color="black")
    from PIL import ImageDraw
    draw = ImageDraw.Draw(img)
    draw.rectangle([200, 150, 1080, 570], fill="white")
    draw.ellipse([540, 260, 740, 460], fill="red")

    duration = 2.5
    fps = 24
    expected_frames = int(round(duration * fps))  # 60 frames

    frames = generate_ken_burns_frames(img, duration_s=duration, fps=fps, zoom_start=1.0, zoom_end=1.08)
    assert len(frames) == expected_frames

    for f in frames:
        assert f.size == (TARGET_WIDTH, TARGET_HEIGHT)

    # First and last frames must have different pixels
    arr_first = np.array(frames[0])
    arr_last = np.array(frames[-1])
    diff = np.abs(arr_first.astype(float) - arr_last.astype(float))
    assert np.mean(diff) > 0.05, "First and last frames should differ due to zoom"

    # Test reverse zoom (zoom out)
    frames_reverse = generate_ken_burns_frames(img, duration_s=1.0, fps=10, reverse=True)
    assert len(frames_reverse) == 10


def test_frames_to_numpy():
    frames = [Image.new("RGB", (1280, 720), color="orange") for _ in range(5)]
    np_frames = frames_to_numpy(frames)
    assert len(np_frames) == 5
    assert np_frames[0].shape == (720, 1280, 3)
    assert np_frames[0].dtype == np.uint8
