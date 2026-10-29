"""Script and caption generation logic (Template + AI mode with strict Fact-Check)."""

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from app.schemas import PropertyInput, Scene, ScriptOutput

logger = logging.getLogger("property_video_gen.script_gen")


def wrap_caption(text: str, max_words_per_line: int = 8) -> str:
    """
    Ensure each line of caption contains at most `max_words_per_line` words.
    Preserves existing newlines where appropriate.
    """
    if not text:
        return ""
    paragraphs = text.strip().splitlines()
    output_lines = []
    for para in paragraphs:
        words = para.strip().split()
        if not words:
            continue
        for i in range(0, len(words), max_words_per_line):
            output_lines.append(" ".join(words[i : i + max_words_per_line]))
    return "\n".join(output_lines)


def truncate_voiceover(text: Optional[str], max_words: int = 25) -> Optional[str]:
    """Ensure voiceover narration is at most `max_words` words per scene."""
    if not text:
        return None
    words = text.strip().split()
    if len(words) <= max_words:
        return " ".join(words)
    return " ".join(words[:max_words])


def generate_template_script(prop: PropertyInput, num_images: int) -> ScriptOutput:
    """
    Generates deterministic promotional script scenes based on supplied inputs:
    - 1 title scene
    - 1 to 5 feature scenes
    - 1 details scene (price/type/bedrooms/area)
    - 1 CTA scene
    Total scenes strictly equals num_images (4 to 8).
    """
    clamped_images = max(4, min(8, num_images))
    scenes: List[Scene] = []

    # Scene 0: Title Scene
    title_caption = wrap_caption(f"{prop.property_name}\n{prop.location}", max_words_per_line=8)
    title_vo = truncate_voiceover(
        f"Welcome to {prop.property_name}, premier living situated in {prop.location}.",
        max_words=25,
    )
    scenes.append(Scene(type="title", image_index=0, caption=title_caption, voiceover=title_vo))

    # Feature Scenes: total available slots for features is clamped_images - 3 (for title, details, cta)
    feature_count = clamped_images - 3
    features_to_use = prop.key_features[:feature_count]
    # If more slots than features, repeat or fill
    while len(features_to_use) < feature_count and prop.key_features:
        features_to_use.append(prop.key_features[len(features_to_use) % len(prop.key_features)])

    current_img_idx = 1
    for feat in features_to_use:
        feat_caption = wrap_caption(feat, max_words_per_line=8)
        feat_vo = truncate_voiceover(
            f"Featuring {feat.lower()}, designed for refined and comfortable living.",
            max_words=25,
        )
        scenes.append(
            Scene(
                type="feature",
                image_index=current_img_idx,
                caption=feat_caption,
                voiceover=feat_vo,
            )
        )
        current_img_idx += 1

    # Details Scene: (price, type, bedrooms, area) - omit any missing optional field
    details_lines = [f"{prop.property_type.value} • {prop.price}"]
    spec_parts = []
    if prop.bedrooms:
        spec_parts.append(prop.bedrooms)
    if prop.area:
        spec_parts.append(prop.area)
    if spec_parts:
        details_lines.append(" • ".join(spec_parts))

    details_caption = wrap_caption("\n".join(details_lines), max_words_per_line=8)

    vo_parts = [f"This {prop.property_type.value.lower()}"]
    if prop.bedrooms:
        vo_parts.append(f"featuring {prop.bedrooms}")
    if prop.area:
        vo_parts.append(f"across {prop.area}")
    vo_parts.append(f"is available now for {prop.price}.")
    details_vo = truncate_voiceover(" ".join(vo_parts), max_words=25)

    scenes.append(
        Scene(
            type="details",
            image_index=current_img_idx,
            caption=details_caption,
            voiceover=details_vo,
        )
    )
    current_img_idx += 1

    # CTA Scene: contact information
    cta_caption = wrap_caption(prop.contact_cta, max_words_per_line=8)
    cta_vo = truncate_voiceover(
        f"Contact today to schedule a private viewing. {prop.contact_cta}",
        max_words=25,
    )
    scenes.append(
        Scene(
            type="cta",
            image_index=current_img_idx,
            caption=cta_caption,
            voiceover=cta_vo,
        )
    )

    return ScriptOutput(scenes=scenes, used_template_fallback=False)


def extract_numbers_and_entities(text: str) -> Tuple[Set[str], Set[str]]:
    """
    Extracts numerical tokens and capitalized entities from text for fact-checking.
    """
    # Extract numbers (integers, decimals, prices, BHK numbers, sq ft values)
    raw_numbers = re.findall(r"\b\d+(?:[.,]\d+)?\b", text)
    numbers = {n.replace(",", "") for n in raw_numbers}

    # Extract capitalized proper words (ignore common sentence starters)
    common_words = {
        "The", "This", "A", "An", "In", "On", "At", "For", "With", "And", "Or",
        "Welcome", "Featuring", "Call", "Visit", "Contact", "Exclusive", "Now",
        "Available", "Offering", "Experience", "Designed", "Your", "Today",
        "Premier", "Luxury", "Modern", "Spacious", "Prime", "Exceptional",
    }
    raw_proper = re.findall(r"\b[A-Z][a-zA-Z0-9'-]+\b", text)
    proper_nouns = {w for w in raw_proper if w not in common_words and len(w) > 2}

    return numbers, proper_nouns


def fact_check_script(prop: PropertyInput, script: ScriptOutput) -> Tuple[bool, Optional[str]]:
    """
    Strict fact-check:
    Every number, price, and proper noun in the generated script must appear in the input.
    No invented amenities, metro distances, ROI, or claims.
    """
    # Compile entire input into a normalized corpus
    input_text = " ".join([
        prop.property_name,
        prop.location,
        prop.price,
        prop.property_type.value,
        prop.bedrooms or "",
        prop.area or "",
        " ".join(prop.key_features),
        prop.contact_cta,
    ])

    input_numbers, input_proper = extract_numbers_and_entities(input_text)
    input_lower = input_text.lower()

    # Hallucination watchwords that must never appear unless in input
    prohibited_claims = ["metro", "station", "roi", "yield", "highway", "airport", "mall", "hospital", "school"]

    for scene in script.scenes:
        scene_text = f"{scene.caption} {scene.voiceover or ''}"
        scene_numbers, scene_proper = extract_numbers_and_entities(scene_text)

        # 1. Check prohibited hallucination watchwords / claims first
        for claim in prohibited_claims:
            if claim in scene_text.lower() and claim not in input_lower:
                return False, f"Invented claim '{claim}' detected in scene {scene.type}"

        # 2. Check numbers
        for num in scene_numbers:
            if num not in input_numbers:
                return False, f"Invented number '{num}' detected in scene {scene.type}"

        # 3. Check proper nouns
        for proper in scene_proper:
            if proper.lower() not in input_lower:
                return False, f"Invented entity or proper noun '{proper}' in scene {scene.type}"

    return True, None


def generate_script(
    prop: PropertyInput,
    num_images: int,
    api_key: Optional[str] = None,
) -> Tuple[ScriptOutput, Optional[str]]:
    """
    Main entry point for script generation.
    Generates via Anthropic API if script_mode == 'ai' and API key is present.
    Strictly validates and fact-checks; falls back to template on any failure.
    """
    warning = None

    if prop.script_mode.value == "ai":
        actual_key = api_key or os.getenv("ANTHROPIC_API_KEY", "").strip()
        if not actual_key:
            warning = "Template fallback used: ANTHROPIC_API_KEY is not configured."
            template_script = generate_template_script(prop, num_images)
            template_script.used_template_fallback = True
            return template_script, warning

        try:
            from anthropic import Anthropic
            client = Anthropic(api_key=actual_key)
            model = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")

            prompt = (
                f"You are a real estate video script generator. Using ONLY the facts provided below, "
                f"generate an MP4 promotional video script consisting of exactly {num_images} scenes.\n"
                f"RULES:\n"
                f"1. DO NOT invent or assume ANY facts, amenities, distances, ROI, landmarks, or near metro claims.\n"
                f"2. Every number, price, bedroom count, and proper name must come strictly from the inputs.\n"
                f"3. Exactly 1 'title' scene (image_index 0), then feature scenes, then 1 'details' scene, then 1 'cta' scene (image_index {num_images - 1}).\n"
                f"4. Captions must be at most 8 words per line.\n"
                f"5. Voiceover must be at most 25 words per scene.\n"
                f"6. Respond ONLY with valid JSON in this schema:\n"
                f'{{"scenes": [{{"type": "title|feature|details|cta", "image_index": 0, "caption": "...", "voiceover": "..."}}]}}\n\n'
                f"INPUTS:\n"
                f"Property Name: {prop.property_name}\n"
                f"Location: {prop.location}\n"
                f"Price: {prop.price}\n"
                f"Type: {prop.property_type.value}\n"
                f"Bedrooms: {prop.bedrooms or 'Not specified'}\n"
                f"Area: {prop.area or 'Not specified'}\n"
                f"Key Features:\n" + "\n".join(f"- {f}" for f in prop.key_features) + "\n"
                f"Contact / CTA: {prop.contact_cta}\n"
            )

            response = client.messages.create(
                model=model,
                max_tokens=1000,
                temperature=0.2,
                system="You are a strict, factual real estate video script assistant. Output JSON only.",
                messages=[{"role": "user", "content": prompt}],
            )

            raw_text = response.content[0].text.strip()
            # Clean markdown codeblocks if enclosed in ```json
            if "```" in raw_text:
                raw_text = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_text, flags=re.MULTILINE).strip()

            parsed = json.loads(raw_text)
            scenes_data = parsed.get("scenes", [])
            if len(scenes_data) != num_images:
                raise ValueError(f"AI returned {len(scenes_data)} scenes, expected {num_images}")

            ai_scenes = []
            for item in scenes_data:
                ai_scenes.append(
                    Scene(
                        type=item["type"],
                        image_index=int(item["image_index"]),
                        caption=wrap_caption(item["caption"]),
                        voiceover=truncate_voiceover(item.get("voiceover")),
                    )
                )

            ai_script = ScriptOutput(scenes=ai_scenes, used_template_fallback=False)

            # Run Fact Check
            is_valid, fail_reason = fact_check_script(prop, ai_script)
            if not is_valid:
                logger.warning(f"AI script failed fact check: {fail_reason}. Falling back to template.")
                warning = f"Template fallback used: {fail_reason}"
                fallback_script = generate_template_script(prop, num_images)
                fallback_script.used_template_fallback = True
                return fallback_script, warning

            return ai_script, None

        except Exception as e:
            logger.warning(f"AI generation failed ({e}). Falling back to template.")
            warning = f"Template fallback used: {str(e)}"
            fallback_script = generate_template_script(prop, num_images)
            fallback_script.used_template_fallback = True
            return fallback_script, warning

    # Default: Template mode
    template_script = generate_template_script(prop, num_images)
    return template_script, None
