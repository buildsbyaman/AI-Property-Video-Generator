"""Validation utilities for property data and uploaded images."""

import io
import json
import os
from typing import Any, Dict, List, Optional, Tuple
from PIL import Image, UnidentifiedImageError

from app.schemas import FieldError, PropertyInput, ValidationErrorResponse

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
DEFAULT_MAX_MB = 8


def parse_and_validate_property_data(form_dict: Dict[str, Any]) -> Tuple[Optional[PropertyInput], List[FieldError]]:
    """
    Validate property data dictionary and return (PropertyInput, list of FieldError).
    Extracts field-level validation errors into the required `{field, message}` format.
    """
    errors: List[FieldError] = []
    
    # Pre-process key_features if provided as string or json
    raw_features = form_dict.get("key_features", [])
    if isinstance(raw_features, str):
        try:
            parsed = json.loads(raw_features)
            if isinstance(parsed, list):
                raw_features = parsed
            else:
                raw_features = [line.strip() for line in raw_features.splitlines() if line.strip()]
        except (json.JSONDecodeError, ValueError):
            raw_features = [line.strip() for line in raw_features.splitlines() if line.strip()]

    # Convert voiceover_enabled boolean if received as string from FormData
    raw_voiceover = form_dict.get("voiceover_enabled", True)
    if isinstance(raw_voiceover, str):
        raw_voiceover = raw_voiceover.lower() in ("true", "1", "yes", "on")

    # Build clean payload for Pydantic
    payload = {
        "property_name": form_dict.get("property_name", ""),
        "location": form_dict.get("location", ""),
        "price": form_dict.get("price", ""),
        "property_type": form_dict.get("property_type", ""),
        "bedrooms": form_dict.get("bedrooms"),
        "area": form_dict.get("area"),
        "key_features": raw_features,
        "contact_cta": form_dict.get("contact_cta", ""),
        "voiceover_enabled": raw_voiceover,
        "script_mode": form_dict.get("script_mode", "template"),
    }

    try:
        prop_input = PropertyInput(**payload)
        return prop_input, []
    except Exception as exc:
        # Pydantic validation error parsing
        from pydantic import ValidationError
        if isinstance(exc, ValidationError):
            for err in exc.errors():
                field_path = err["loc"][0] if err["loc"] else "general"
                # Strip leading "Value error, " if present in message
                msg = err["msg"]
                if msg.startswith("Value error, "):
                    msg = msg[len("Value error, "):]
                errors.append(FieldError(field=str(field_path), message=msg))
        else:
            errors.append(FieldError(field="general", message=str(exc)))
        return None, errors


def validate_and_filter_images(
    files: List[Tuple[str, bytes, str]],  # (filename, content_bytes, content_type)
    max_mb: Optional[int] = None,
) -> Tuple[List[Tuple[str, bytes]], List[str], List[FieldError]]:
    """
    Validates uploaded images according to FR-1:
    - Checks file count (4 to 8 required)
    - Checks file size (<= max_mb)
    - Checks file format/corrupt images
    - Trims to first 8 with warning if > 8
    - Skips corrupt files with warning if >= 4 valid images remain
    
    Returns:
        (valid_images, warnings, errors)
        valid_images: List of (filename, bytes)
        warnings: List of warning message strings
        errors: List of FieldError objects
    """
    if max_mb is None:
        max_mb = int(os.getenv("MAX_UPLOAD_MB", DEFAULT_MAX_MB))
    max_bytes = max_mb * 1024 * 1024

    warnings: List[str] = []
    errors: List[FieldError] = []

    if not files or len(files) < 4:
        errors.append(FieldError(
            field="images",
            message=f"At least 4 images are required (received {len(files) if files else 0}).",
        ))
        return [], warnings, errors

    # Check for > 8 images
    if len(files) > 8:
        warnings.append(f"Received {len(files)} images; only the first 8 will be used.")
        files = files[:8]

    valid_images: List[Tuple[str, bytes]] = []

    for filename, content, content_type in files:
        # Check size
        if len(content) > max_bytes:
            warnings.append(f"Image '{filename}' exceeds {max_mb} MB limit and was skipped.")
            continue

        # Check content type / extension
        ext = os.path.splitext(filename.lower())[1]
        if ext not in ALLOWED_EXTENSIONS and content_type not in ALLOWED_IMAGE_TYPES:
            warnings.append(f"Image '{filename}' has unsupported format ({ext}) and was skipped.")
            continue

        # Check readability with Pillow (FR-1: Corrupt/unreadable image -> skip, warn)
        try:
            with Image.open(io.BytesIO(content)) as img:
                img.verify()  # verify integrity
            valid_images.append((filename, content))
        except Exception:
            warnings.append(f"Image '{filename}' is corrupt or unreadable and was skipped.")

    if len(valid_images) < 4:
        errors.append(FieldError(
            field="images",
            message=f"Only {len(valid_images)} valid image(s) could be read. At least 4 valid images are required.",
        ))
        return [], warnings, errors

    return valid_images, warnings, errors
