import os
from pathlib import Path
from moviepy import VideoFileClip
from PIL import Image

from app.schemas import Scene
from app.video import assemble_and_export_video, calculate_scene_durations


def test_calculate_scene_durations_scaling():
    # 4 scenes with no voiceover -> should scale up to reach at least 20s
    scenes_4 = [
        Scene(type="title", image_index=0, caption="Title"),
        Scene(type="feature", image_index=1, caption="Feat 1"),
        Scene(type="details", image_index=2, caption="Details"),
        Scene(type="cta", image_index=3, caption="CTA"),
    ]
    durs_4 = calculate_scene_durations(scenes_4, [None, None, None, None])
    total_4 = sum(durs_4) - (len(scenes_4) - 1) * 0.5
    assert total_4 >= 20.0
    for d in durs_4:
        assert 3.0 <= d <= 6.0

    # 8 scenes with long voiceover (e.g. 5.5s each) -> should scale to not exceed 40s
    scenes_8 = [Scene(type="feature", image_index=i, caption=f"Feat {i}") for i in range(8)]
    durs_8 = calculate_scene_durations(scenes_8, [5.5] * 8)
    total_8 = sum(durs_8) - (len(scenes_8) - 1) * 0.5
    assert total_8 <= 40.0
    for d in durs_8:
        assert 3.0 <= d <= 6.0


def test_assemble_and_export_video_e2e(tmp_path):
    # Create 4 test images
    test_images = []
    colors = ["#1A365D", "#234E52", "#742A2A", "#285E61"]
    for c in colors:
        img = Image.new("RGB", (1280, 720), color=c)
        test_images.append(img)

    scenes = [
        Scene(type="title", image_index=0, caption="Test Property\nPrime Location"),
        Scene(type="feature", image_index=1, caption="✦ Infinity Swimming Pool"),
        Scene(type="details", image_index=2, caption="Villa • $1,250,000\n3 BHK"),
        Scene(type="cta", image_index=3, caption="Contact Us Today"),
    ]

    out_mp4 = tmp_path / "test_video.mp4"
    bg_audio = Path("assets/audio/background.mp3")

    progress_log = []

    def on_progress(pct, stage, msg):
        progress_log.append((pct, stage))

    duration = assemble_and_export_video(
        scenes=scenes,
        images=test_images,
        voiceover_paths=[None, None, None, None],
        voiceover_durations=[None, None, None, None],
        background_audio_path=bg_audio,
        output_path=out_mp4,
        progress_callback=on_progress,
    )

    # 1. Output file exists
    assert out_mp4.exists()
    assert os.path.getsize(out_mp4) > 10000

    # 2. Check video properties using MoviePy
    clip = VideoFileClip(str(out_mp4))
    assert clip.size == [1280, 720]
    assert 20.0 <= clip.duration <= 40.0
    assert clip.audio is not None
    clip.close()

    # 3. Check progress callback tracked stages
    stages = [item[1] for item in progress_log]
    assert "rendering" in stages
    assert "done" in stages
