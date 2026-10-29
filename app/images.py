"""Image processing pipeline: validation, cover-cropping to 16:9 (1280x720), and Ken Burns zoom frames."""

import io
import logging
from pathlib import Path
from typing import List, Optional, Tuple, Union

import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

logger = logging.getLogger("property_video_gen.images")

TARGET_WIDTH = 1280
TARGET_HEIGHT = 720
TARGET_ASPECT = TARGET_WIDTH / TARGET_HEIGHT  # 16:9 = 1.7777...


def open_and_normalize_image(source: Union[bytes, str, Path]) -> Optional[Image.Image]:
    """
    Safely opens an image from bytes or file path, applies EXIF orientation,
    and converts to standard 8-bit RGB mode.
    Returns None if the image is corrupt or unreadable.
    """
    try:
        if isinstance(source, (str, Path)):
            img = Image.open(source)
        elif isinstance(source, bytes):
            img = Image.open(io.BytesIO(source))
        else:
            return None

        # Handle EXIF orientation (e.g. phone photos taken vertically)
        img = ImageOps.exif_transpose(img)

        # Convert to RGB if necessary (e.g. RGBA, CMYK, P, L)
        if img.mode != "RGB":
            # If RGBA, paste on black or composite
            if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
                bg = Image.new("RGB", img.size, (11, 11, 11))
                alpha = img.convert("RGBA").split()[-1]
                bg.paste(img.convert("RGB"), mask=alpha)
                img = bg
            else:
                img = img.convert("RGB")

        return img
    except Exception as e:
        logger.warning(f"Failed to open image: {e}")
        return None


def cover_crop(
    img: Image.Image,
    target_width: int = TARGET_WIDTH,
    target_height: int = TARGET_HEIGHT,
) -> Image.Image:
    """
    Resizes and center-crops an image to exact target dimensions (16:9, 1280x720)
    without stretching, distorting, or adding black bars.
    """
    orig_w, orig_h = img.size
    orig_aspect = orig_w / orig_h
    target_aspect = target_width / target_height

    if orig_aspect > target_aspect:
        # Image is wider than 16:9 -> scale height to match, crop excess width
        scale = target_height / orig_h
        new_w = int(round(orig_w * scale))
        new_h = target_height
        resized = img.resize((new_w, new_h), Image.Resampling.BILINEAR)

        # Center crop horizontally
        left = (new_w - target_width) // 2
        crop_box = (left, 0, left + target_width, target_height)
        return resized.crop(crop_box)
    else:
        # Image is taller than 16:9 -> scale width to match, crop excess height
        scale = target_width / orig_w
        new_w = target_width
        new_h = int(round(orig_h * scale))
        resized = img.resize((new_w, new_h), Image.Resampling.BILINEAR)

        # Center crop vertically
        top = (new_h - target_height) // 2
        crop_box = (0, top, target_width, top + target_height)
        return resized.crop(crop_box)


def generate_ken_burns_frames(
    img: Image.Image,
    duration_s: float,
    fps: int = 24,
    zoom_start: float = 1.0,
    zoom_end: float = 1.06,
    target_width: int = TARGET_WIDTH,
    target_height: int = TARGET_HEIGHT,
    reverse: bool = False,
) -> List[Image.Image]:
    """
    Generates a list of Pillow Image frames demonstrating a gentle Ken Burns zoom.
    
    Args:
        img: Base image (already cover-cropped to target_width x target_height, or uncropped).
        duration_s: Duration of the scene in seconds.
        fps: Frames per second (default 24).
        zoom_start: Initial zoom scale factor (default 1.0).
        zoom_end: Ending zoom scale factor (default 1.06 for subtle 6% zoom).
        target_width: Desired frame width (1280).
        target_height: Desired frame height (720).
        reverse: If True, zooms out from zoom_end to zoom_start.
        
    Returns:
        List of Image.Image frames of size (target_width, target_height).
    """
    # First ensure base image is cover-cropped
    base = cover_crop(img, target_width, target_height)
    w, h = base.size

    total_frames = max(1, int(round(duration_s * fps)))
    frames: List[Image.Image] = []

    # If reverse, swap start and end
    z_start, z_end = (zoom_end, zoom_start) if reverse else (zoom_start, zoom_end)

    for i in range(total_frames):
        # Linear interpolation parameter t in [0.0, 1.0]
        t = i / (total_frames - 1) if total_frames > 1 else 0.0
        # Smooth ease-in-out curve
        smooth_t = t * t * (3.0 - 2.0 * t)
        current_zoom = z_start + (z_end - z_start) * smooth_t

        if abs(current_zoom - 1.0) < 1e-4:
            frames.append(base.copy())
            continue

        # Sub-crop size to maintain 16:9 aspect ratio while zooming
        crop_w = w / current_zoom
        crop_h = h / current_zoom

        # Center coordinates
        cx, cy = w / 2.0, h / 2.0
        left = max(0.0, cx - crop_w / 2.0)
        top = max(0.0, cy - crop_h / 2.0)
        right = min(float(w), left + crop_w)
        bottom = min(float(h), top + crop_h)

        cropped = base.crop((int(left), int(top), int(right), int(bottom)))
        frame = cropped.resize((target_width, target_height), Image.Resampling.BILINEAR)
        frames.append(frame)

    return frames


def frames_to_numpy(frames: List[Image.Image]) -> List[np.ndarray]:
    """Converts a list of PIL Image frames into RGB numpy arrays suitable for MoviePy."""
    return [np.array(f) for f in frames]
