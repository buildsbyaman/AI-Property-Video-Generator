import os
from pathlib import Path
from unittest.mock import patch

import pytest
from app.schemas import Scene
from app.tts import (
    get_audio_duration,
    synthesize_scene_voiceover,
    synthesize_script_voiceovers,
)


def test_background_audio_duration():
    bg_path = Path("assets/audio/background.mp3")
    assert bg_path.exists(), "assets/audio/background.mp3 should exist"
    dur = get_audio_duration(bg_path)
    assert 29.0 <= dur <= 31.0, f"Background audio expected ~30s, got {dur}"


def test_empty_or_disabled_tts(tmp_path):
    out_file = tmp_path / "test_empty.mp3"

    # Empty text
    path, dur, warn = synthesize_scene_voiceover("", out_file)
    assert path is None
    assert dur is None
    assert warn is None

    # Disabled via environment
    with patch.dict(os.environ, {"ENABLE_TTS": "false"}):
        path, dur, warn = synthesize_scene_voiceover("Some text", out_file)
        assert path is None
        assert dur is None


def test_synthesize_scene_voiceover_success(tmp_path):
    out_file = tmp_path / "voiceover.mp3"
    text = "Welcome to Azure Crest Residences."

    path, dur, warn = synthesize_scene_voiceover(text, out_file)
    assert path is not None
    assert os.path.exists(path)
    assert dur is not None
    assert dur > 1.0


def test_synthesize_graceful_degradation_on_network_failure(tmp_path):
    out_file = tmp_path / "fail.mp3"

    # Mock edge-tts and gTTS to simulate offline / network error
    with patch("app.tts._run_edge_tts_sync", side_effect=ConnectionError("Offline")), \
         patch("gtts.gTTS.save", side_effect=ConnectionError("Offline")):
        path, dur, warn = synthesize_scene_voiceover("Test narration text", out_file)
        assert path is None
        assert dur is None
        assert warn is not None
        assert "Voice-over disabled: network failure" in warn


def test_synthesize_script_voiceovers_batch(tmp_path):
    scenes = [
        Scene(type="title", image_index=0, caption="Title", voiceover="Welcome to the property."),
        Scene(type="feature", image_index=1, caption="Feature 1", voiceover=None),
        Scene(type="cta", image_index=2, caption="CTA", voiceover="Contact us today."),
    ]

    paths, durs, warns = synthesize_script_voiceovers(scenes, tmp_path, voiceover_enabled=True)
    assert len(paths) == 3
    assert len(durs) == 3
    assert paths[1] is None  # Scene without voiceover
    assert paths[0] is not None
    assert paths[2] is not None
