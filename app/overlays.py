"""Pillow text and caption overlay rendering pipeline.
Creates readable semi-transparent dark bars with orange accent lines and crisp typography."""

import os
from pathlib import Path
from typing import List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

BASE_DIR = Path(__file__).resolve().parent.parent
FONTS_DIR = BASE_DIR / "assets" / "fonts"

# Design spec colors
BG_BAR_COLOR = (11, 11, 11, 215)        # Semi-transparent dark #0B0B0B at ~84% opacity
ACCENT_ORANGE = (255, 106, 26, 255)     # Brand accent #FF6A1A
TEXT_WHITE = (245, 245, 245, 255)       # Crisp white #F5F5F5
TEXT_MUTED = (180, 180, 180, 255)       # Muted subtitle #B4B4B4

_FONT_CACHE = {}


def get_font(size: int = 34) -> ImageFont.ImageFont:
    """Retrieves or caches a TTF font matching the Inter design spec."""
    if size in _FONT_CACHE:
        return _FONT_CACHE[size]

    candidates = [
        FONTS_DIR / "Inter.ttf",
        FONTS_DIR / "Inter-Regular.ttf",
        Path("/System/Library/Fonts/SFNS.ttf"),
        Path("/System/Library/Fonts/Helvetica.ttc"),
        Path("/Library/Fonts/Arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]

    for candidate in candidates:
        if candidate.exists():
            try:
                font = ImageFont.truetype(str(candidate), size)
                _FONT_CACHE[size] = font
                return font
            except Exception:
                continue

    # Fallback to Pillow default
    fallback = ImageFont.load_default()
    _FONT_CACHE[size] = fallback
    return fallback


def create_overlay_layer(
    caption: str,
    scene_type: str = "feature",
    width: int = 1280,
    height: int = 720,
) -> Image.Image:
    """
    Renders the semi-transparent dark bar, orange accent line, and text onto
    a separate RGBA layer of size (width, height).
    This overlay layer can be composited rapidly over Ken Burns video frames.
    """
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    clean_caption = caption.strip() if caption else ""
    lines = [line.strip() for line in clean_caption.splitlines() if line.strip()]

    if not lines:
        return overlay

    # Typography sizing based on scene type and line count
    if scene_type == "title":
        title_font = get_font(38)
        sub_font = get_font(26)
        line_height_1 = 44
        line_height_2 = 32
        total_text_h = line_height_1 + (line_height_2 if len(lines) > 1 else 0)
    elif scene_type == "details":
        main_font = get_font(34)
        sub_font = get_font(28)
        line_height_1 = 40
        line_height_2 = 34
        total_text_h = line_height_1 + (line_height_2 if len(lines) > 1 else 0)
    else:
        # Features or CTA
        font_size = 34 if len(lines) <= 2 else 28
        main_font = get_font(font_size)
        sub_font = main_font
        line_height_1 = font_size + 10
        line_height_2 = line_height_1
        total_text_h = len(lines) * line_height_1

    # Calculate bar height and position
    padding_y = 26
    bar_height = max(110, total_text_h + (padding_y * 2))
    bar_top = height - bar_height

    # 1. Draw semi-transparent dark bar
    draw.rectangle([0, bar_top, width, height], fill=BG_BAR_COLOR)

    # 2. Draw 3.5px orange accent line at the top of the bar
    accent_height = 4
    draw.rectangle([0, bar_top, width, bar_top + accent_height], fill=ACCENT_ORANGE)

    # 3. Draw text lines centered horizontally
    current_y = bar_top + padding_y + 4

    for idx, line in enumerate(lines):
        if scene_type == "title":
            f = title_font if idx == 0 else sub_font
            col = TEXT_WHITE if idx == 0 else TEXT_MUTED
            lh = line_height_1 if idx == 0 else line_height_2
        elif scene_type == "details":
            f = main_font if idx == 0 else sub_font
            col = TEXT_WHITE
            lh = line_height_1 if idx == 0 else line_height_2
        else:
            f = main_font
            col = TEXT_WHITE
            lh = line_height_1

        # Calculate text width using getbbox for centering
        bbox = f.getbbox(line)
        text_w = bbox[2] - bbox[0]
        text_x = max(20, (width - text_w) // 2)

        # Draw text
        draw.text((text_x, current_y), line, font=f, fill=col)
        current_y += lh

    return overlay


def draw_caption_overlay(
    base_img: Image.Image,
    caption: str,
    scene_type: str = "feature",
) -> Image.Image:
    """
    Composites the caption overlay onto a single base image.
    Guarantees readable contrast on any background.
    """
    w, h = base_img.size
    overlay = create_overlay_layer(caption, scene_type=scene_type, width=w, height=h)

    result = base_img.convert("RGBA")
    result.alpha_composite(overlay)
    return result.convert("RGB")


def apply_overlay_to_frames(
    frames: List[Image.Image],
    caption: str,
    scene_type: str = "feature",
) -> List[Image.Image]:
    """
    Applies the caption overlay across a list of Ken Burns frames efficiently.
    Pre-renders the overlay canvas once, then alpha-composites across all frames.
    """
    if not frames:
        return []

    w, h = frames[0].size
    overlay = create_overlay_layer(caption, scene_type=scene_type, width=w, height=h)

    composited_frames: List[Image.Image] = []
    for frame in frames:
        rgba = frame.convert("RGBA")
        rgba.alpha_composite(overlay)
        composited_frames.append(rgba.convert("RGB"))

    return composited_frames
