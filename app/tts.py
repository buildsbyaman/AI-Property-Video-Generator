"""Voice-over synthesis wrapper using edge-tts with gTTS fallback and silent degradation."""

import asyncio
import concurrent.futures
import logging
import os
from pathlib import Path
from typing import List, Optional, Tuple

from moviepy import AudioFileClip

from app.schemas import Scene

logger = logging.getLogger("property_video_gen.tts")

DEFAULT_VOICE = "en-US-ChristopherNeural"


def get_audio_duration(file_path: Union_Path) -> float:
    """Measures exact duration of an audio file in seconds using MoviePy."""
    clip = AudioFileClip(str(file_path))
    duration = float(clip.duration)
    clip.close()
    return duration


# Type alias for path
Union_Path = Path | str


def _run_edge_tts_sync(text: str, out_file: str, voice: str = DEFAULT_VOICE, timeout_s: float = 12.0) -> None:
    """Runs edge-tts async coroutine safely within any thread context."""
    import edge_tts

    async def _save():
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(out_file)

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    if loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(asyncio.run, _save()).result(timeout=timeout_s)
    else:
        loop.run_until_complete(_save())


def synthesize_scene_voiceover(
    text: Optional[str],
    output_path: Union_Path,
    voice: str = DEFAULT_VOICE,
) -> Tuple[Optional[str], Optional[float], Optional[str]]:
    """
    Synthesizes speech for a single scene voice-over line.
    Tries edge-tts first; falls back to gTTS on failure; degrades to silent on complete network failure.
    
    Returns:
        (saved_audio_path, duration_seconds, warning_message)
    """
    enable_tts = os.getenv("ENABLE_TTS", "true").lower() in ("true", "1", "yes")
    if not enable_tts or not text or not text.strip():
        return None, None, None

    clean_text = text.strip()
    out_str = str(output_path)
    warning = None

    # 1. Try edge-tts
    try:
        _run_edge_tts_sync(clean_text, out_str, voice=voice)
        duration = get_audio_duration(out_str)
        return out_str, duration, None
    except Exception as edge_err:
        logger.warning(f"edge-tts failed ({edge_err}), falling back to gTTS")
        warning = f"Notice: edge-tts voice synthesis unavailable ({type(edge_err).__name__}), used gTTS fallback."

    # 2. Try gTTS fallback
    try:
        from gtts import gTTS
        tts = gTTS(text=clean_text, lang="en")
        tts.save(out_str)
        duration = get_audio_duration(out_str)
        return out_str, duration, warning
    except Exception as gtts_err:
        logger.warning(f"gTTS fallback also failed ({gtts_err}). Continuing without voiceover.")
        # If file was partially created, clean up
        if os.path.exists(out_str):
            try:
                os.remove(out_str)
            except OSError:
                pass
        return None, None, f"Voice-over disabled: network failure ({type(gtts_err).__name__}). Video generated without narration."


def synthesize_script_voiceovers(
    scenes: List[Scene],
    output_dir: Path,
    voiceover_enabled: bool = True,
) -> Tuple[List[Optional[str]], List[Optional[float]], List[str]]:
    """
    Synthesizes audio for all scenes in a script.
    
    Returns:
        (audio_paths, durations, warnings)
    """
    audio_paths: List[Optional[str]] = []
    durations: List[Optional[float]] = []
    warnings: List[str] = []

    if not voiceover_enabled or os.getenv("ENABLE_TTS", "true").lower() not in ("true", "1", "yes"):
        return [None] * len(scenes), [None] * len(scenes), warnings

    output_dir.mkdir(parents=True, exist_ok=True)

    for i, scene in enumerate(scenes):
        if not scene.voiceover:
            audio_paths.append(None)
            durations.append(None)
            continue

        scene_audio_path = output_dir / f"voiceover_scene_{i}.mp3"
        path, dur, warn = synthesize_scene_voiceover(scene.voiceover, scene_audio_path)

        audio_paths.append(path)
        durations.append(dur)
        if warn and warn not in warnings:
            warnings.append(warn)

    return audio_paths, durations, warnings
