"""Video assembly and export pipeline using MoviePy 2.x and Pillow.
Handles Ken Burns motion, 0.5s scene crossfades, background audio ducking, and H.264/AAC export."""

import logging
import os
from pathlib import Path
from typing import Callable, List, Optional, Tuple

import numpy as np
from moviepy import (
    AudioFileClip,
    CompositeAudioClip,
    CompositeVideoClip,
    ImageSequenceClip,
)
import moviepy.audio.fx as afx
import moviepy.video.fx as vfx
from PIL import Image

from app.images import (
    TARGET_HEIGHT,
    TARGET_WIDTH,
    frames_to_numpy,
    generate_ken_burns_frames,
    open_and_normalize_image,
)
from app.overlays import apply_overlay_to_frames
from app.schemas import Scene

logger = logging.getLogger("property_video_gen.video")

CROSSFADE_DURATION = 0.5  # 0.5s crossfade between scenes
FPS = 24
MIN_TOTAL_DURATION = 20.0
MAX_TOTAL_DURATION = 40.0
MIN_SCENE_DURATION = 3.0
MAX_SCENE_DURATION = 6.0


def calculate_scene_durations(
    scenes: List[Scene],
    voiceover_durations: List[Optional[float]],
) -> List[float]:
    """
    Computes duration for each scene so that:
    - Each scene is between 3.0s and 6.0s
    - Narration has enough time to complete comfortably
    - Total duration after crossfades is strictly between 20.0s and 40.0s
    """
    n = len(scenes)
    durations = []

    # 1. Base duration calculation
    for i in range(n):
        vo_dur = voiceover_durations[i] if i < len(voiceover_durations) else None
        if vo_dur and vo_dur > 0:
            # Leave 0.5s padding for voiceover to finish comfortably
            dur = max(MIN_SCENE_DURATION, min(MAX_SCENE_DURATION, vo_dur + 0.6))
        else:
            dur = 4.0
        durations.append(dur)

    # 2. Compute total video duration after (n - 1) crossfades of 0.5s
    # Total = sum(durations) - (n - 1) * 0.5
    crossfade_loss = (n - 1) * CROSSFADE_DURATION
    total = sum(durations) - crossfade_loss

    # 3. Adjust if outside [MIN_TOTAL_DURATION, MAX_TOTAL_DURATION]
    if total < MIN_TOTAL_DURATION:
        shortfall = MIN_TOTAL_DURATION - total
        per_scene_add = shortfall / n
        durations = [min(MAX_SCENE_DURATION, d + per_scene_add) for d in durations]
    elif total > MAX_TOTAL_DURATION:
        excess = total - MAX_TOTAL_DURATION
        per_scene_sub = excess / n
        durations = [max(MIN_SCENE_DURATION, d - per_scene_sub) for d in durations]

    return durations


def assemble_and_export_video(
    scenes: List[Scene],
    images: List[Image.Image],
    voiceover_paths: List[Optional[str]],
    voiceover_durations: List[Optional[float]],
    background_audio_path: Path,
    output_path: Path,
    progress_callback: Optional[Callable[[int, str, str], None]] = None,
) -> float:
    """
    Assembles video scenes with Ken Burns zoom, caption overlays, 0.5s crossfades,
    mixes ducked background audio, and exports MP4.
    
    Returns:
        final_video_duration (float) in seconds.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    num_scenes = len(scenes)

    # Step 1: Calculate scene durations
    scene_durations = calculate_scene_durations(scenes, voiceover_durations)

    if progress_callback:
        progress_callback(10, "rendering", "Computed scene timings. Generating visual frames...")

    video_clips = []
    audio_tracks = []
    current_start_time = 0.0

    # Step 2: Build scene clips
    for i, scene in enumerate(scenes):
        duration = scene_durations[i]
        img_idx = scene.image_index if scene.image_index < len(images) else (i % len(images))
        base_img = images[img_idx]

        # Alternate zoom direction: even scenes zoom in, odd scenes zoom out
        zoom_reverse = (i % 2 == 1)

        # 2a. Generate Ken Burns frames
        raw_frames = generate_ken_burns_frames(
            base_img,
            duration_s=duration,
            fps=FPS,
            zoom_start=1.0,
            zoom_end=1.06,
            reverse=zoom_reverse,
        )

        # 2b. Overlay captions
        captioned_frames = apply_overlay_to_frames(
            raw_frames,
            caption=scene.caption,
            scene_type=scene.type,
        )

        # 2c. Convert to numpy array & MoviePy clip
        np_frames = frames_to_numpy(captioned_frames)
        scene_clip = ImageSequenceClip(np_frames, fps=FPS)

        # 2d. Apply crossfade (all scenes after scene 0 crossfade in over 0.5s)
        if i > 0:
            scene_clip = scene_clip.with_effects([vfx.CrossFadeIn(CROSSFADE_DURATION)])

        scene_clip = scene_clip.with_start(current_start_time)
        video_clips.append(scene_clip)

        # 2e. Attach scene voiceover if present
        vo_path = voiceover_paths[i] if i < len(voiceover_paths) else None
        if vo_path and os.path.exists(vo_path):
            try:
                vo_clip = AudioFileClip(str(vo_path))
                # Start voiceover 0.2s into the scene
                vo_clip = vo_clip.with_start(current_start_time + 0.2)
                audio_tracks.append(vo_clip)
            except Exception as e:
                logger.warning(f"Could not load voiceover audio for scene {i}: {e}")

        # Advance start time for next scene (subtracting crossfade duration)
        current_start_time += duration - CROSSFADE_DURATION

        if progress_callback:
            pct = 10 + int(60 * ((i + 1) / num_scenes))
            progress_callback(pct, "rendering", f"Rendered scene {i + 1} of {num_scenes}...")

    # Step 3: Composite Video
    final_video = CompositeVideoClip(video_clips, size=(TARGET_WIDTH, TARGET_HEIGHT))
    total_video_duration = final_video.duration

    if progress_callback:
        progress_callback(75, "rendering", "Mixing background audio and ducking voice-over...")

    # Step 4: Mix Audio
    if background_audio_path and background_audio_path.exists():
        try:
            bg_audio = AudioFileClip(str(background_audio_path))
            if bg_audio.duration < total_video_duration:
                bg_audio = bg_audio.with_effects([afx.AudioLoop(duration=total_video_duration)])
            else:
                bg_audio = bg_audio.subclipped(0, total_video_duration)

            # Ducking: volume at 12% under voiceover, 15% otherwise
            ducked_volume = 0.12 if audio_tracks else 0.15
            bg_audio = bg_audio.with_effects([
                afx.MultiplyVolume(ducked_volume),
                afx.AudioFadeOut(1.5),  # fade out in final 1.5s
            ])
            audio_tracks.insert(0, bg_audio)
        except Exception as e:
            logger.warning(f"Failed to mix background audio: {e}")

    if audio_tracks:
        composite_audio = CompositeAudioClip(audio_tracks)
        final_video = final_video.with_audio(composite_audio)

    # Step 5: Export MP4 (1280x720, 24 fps, H.264 + AAC)
    if progress_callback:
        progress_callback(85, "rendering", "Encoding H.264/AAC MP4 video...")

    final_video.write_videofile(
        str(output_path),
        fps=FPS,
        codec="libx264",
        audio_codec="aac",
        logger=None,
    )

    # Close clips to free resources
    try:
        final_video.close()
        for c in video_clips:
            c.close()
        for a in audio_tracks:
            a.close()
    except Exception:
        pass

    if progress_callback:
        progress_callback(100, "done", "Video export complete.")

    return total_video_duration
