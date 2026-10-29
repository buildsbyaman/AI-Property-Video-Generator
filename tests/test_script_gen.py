import pytest
from app.schemas import PropertyInput, PropertyType, Scene, ScriptMode, ScriptOutput
from app.script_gen import (
    fact_check_script,
    generate_script,
    generate_template_script,
    truncate_voiceover,
    wrap_caption,
)


@pytest.fixture
def sample_property() -> PropertyInput:
    return PropertyInput(
        property_name="Silver Oak Manor",
        location="Greenwood Hills, CA",
        price="$1,450,000",
        property_type=PropertyType.HOUSE,
        bedrooms="4 Beds",
        area="2,800 sq ft",
        key_features=[
            "Gourmet Chef Kitchen",
            "Heated Saltwater Pool",
            "Panoramic Mountain Views",
            "Spacious Redwood Deck",
        ],
        contact_cta="Call 555-0199 or visit silveroak.com",
        voiceover_enabled=True,
        script_mode=ScriptMode.TEMPLATE,
    )


def test_wrap_caption_and_truncate_voiceover():
    # Long caption without newlines should wrap at 8 words
    long_caption = "One two three four five six seven eight nine ten eleven twelve"
    wrapped = wrap_caption(long_caption, max_words_per_line=8)
    lines = wrapped.splitlines()
    assert len(lines) == 2
    assert len(lines[0].split()) == 8
    assert len(lines[1].split()) == 4

    # Voiceover over 25 words should truncate to 25
    long_vo = " ".join([f"word{i}" for i in range(40)])
    truncated = truncate_voiceover(long_vo, max_words=25)
    assert len(truncated.split()) == 25


def test_template_script_structure_and_constraints(sample_property):
    # Test for 4, 6, and 8 images
    for count in [4, 6, 8]:
        script = generate_template_script(sample_property, num_images=count)
        assert len(script.scenes) == count
        assert script.scenes[0].type == "title"
        assert script.scenes[0].image_index == 0
        assert script.scenes[-1].type == "cta"
        assert script.scenes[-1].image_index == count - 1
        assert script.scenes[-2].type == "details"
        assert script.scenes[-2].image_index == count - 2

        # Verify captions <= 8 words per line
        for s in script.scenes:
            for line in s.caption.splitlines():
                assert len(line.split()) <= 8

        # Verify voiceover <= 25 words
        for s in script.scenes:
            if s.voiceover:
                assert len(s.voiceover.split()) <= 25


def test_template_script_omits_missing_optional_fields():
    prop_no_opts = PropertyInput(
        property_name="Downtown Studio Loft",
        location="Arts District",
        price="$320,000",
        property_type=PropertyType.APARTMENT,
        bedrooms=None,
        area=None,
        key_features=["Polished Concrete Floors", "Exposed Brick Walls", "14-foot Ceilings"],
        contact_cta="Email sales@loftarts.com",
        voiceover_enabled=True,
        script_mode=ScriptMode.TEMPLATE,
    )
    script = generate_template_script(prop_no_opts, num_images=4)
    details_scene = [s for s in script.scenes if s.type == "details"][0]
    # Ensure "None" or "null" never appear
    assert "None" not in details_scene.caption
    assert "none" not in details_scene.caption.lower()
    assert "None" not in (details_scene.voiceover or "")


def test_fact_check_valid_script(sample_property):
    script = generate_template_script(sample_property, num_images=6)
    is_valid, reason = fact_check_script(sample_property, script)
    assert is_valid is True
    assert reason is None


def test_fact_check_detects_invented_claims(sample_property):
    # Case 1: Invented metro station claim
    bad_scenes = [
        Scene(type="title", image_index=0, caption="Silver Oak Manor", voiceover="Welcome."),
        Scene(type="feature", image_index=1, caption="Convenient Living", voiceover="Only 2 minutes to the metro station."),
        Scene(type="details", image_index=2, caption="House $1,450,000", voiceover="Offered at $1,450,000."),
        Scene(type="cta", image_index=3, caption="Call 555-0199", voiceover="Call 555-0199."),
    ]
    bad_script = ScriptOutput(scenes=bad_scenes)
    is_valid, reason = fact_check_script(sample_property, bad_script)
    assert is_valid is False
    assert "metro" in reason.lower()


def test_fact_check_detects_invented_number(sample_property):
    # Case 2: Invented number (e.g. 99% ROI)
    bad_scenes = [
        Scene(type="title", image_index=0, caption="Silver Oak Manor", voiceover="Welcome."),
        Scene(type="feature", image_index=1, caption="High Returns", voiceover="Guaranteed 99% rental return."),
        Scene(type="details", image_index=2, caption="House $1,450,000", voiceover="Offered at $1,450,000."),
        Scene(type="cta", image_index=3, caption="Call 555-0199", voiceover="Call 555-0199."),
    ]
    bad_script = ScriptOutput(scenes=bad_scenes)
    is_valid, reason = fact_check_script(sample_property, bad_script)
    assert is_valid is False
    assert "99" in reason


def test_ai_mode_fallback_without_key(sample_property):
    sample_property.script_mode = ScriptMode.AI
    script, warning = generate_script(sample_property, num_images=5, api_key="")
    assert script.used_template_fallback is True
    assert len(script.scenes) == 5
    assert warning is not None
    assert "Template fallback used" in warning
