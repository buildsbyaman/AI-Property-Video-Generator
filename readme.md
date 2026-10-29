# AI Property Video Generator

Turn property details and photos into a short, ready-to-share promotional video, with no video editor needed.
Enter the details in a web form, upload 4-8 images, and get an MP4 with captions, transitions, background music and optional voice-over.

## Features

- Simple dark (black + orange) web UI with drag-and-drop image upload
- Script and captions from **template logic** (default, works offline) or an **optional LLM**
- Fact check: AI-written lines are rejected if they contain facts not in your input, and the app falls back to templates
- Ken Burns motion, crossfades, readable caption overlays
- Optional voice-over (edge-tts, gTTS fallback) and royalty-free background audio
- Live progress, in-browser preview, one-click MP4 download
- Graceful handling of missing/corrupt images and missing details

## Quick Start

### Prerequisites

- Python 3.11+
- FFmpeg (bundled via `imageio-ffmpeg`; a system install is also fine)

### Install

```bash
git clone <your-repo-url>
cd property-video-generator
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # optional: add ANTHROPIC_API_KEY for AI script mode
```

### Run

```bash
uvicorn app.main:app --reload --port 8000
```

Open http://localhost:8000, click **Load sample data**, then **Generate video**.

## Configuration (`.env`)

| Variable            | Required | Purpose                                                 |
| ------------------- | -------- | ------------------------------------------------------- |
| `ANTHROPIC_API_KEY` | No       | Enables AI script mode. Without it, templates are used. |
| `ANTHROPIC_MODEL`   | No       | Model name for AI script mode (see `.env.example`)      |
| `ENABLE_TTS`        | No       | `true`/`false`, default `true`                          |
| `MAX_UPLOAD_MB`     | No       | Per-image limit, default `8`                            |

Never commit `.env`. Use only synthetic data and no real customer information.

## How It Works

1. **Validate** inputs and images (type, size, count, readability).
2. **Script**: build a scene plan (title -> features -> details -> CTA). Template mode fills fixed sentence patterns. AI mode asks the model for JSON using only your supplied fields, then checks every number and name against the input.
3. **Narrate** (optional): synthesise one audio clip per scene and measure its length.
4. **Render**: cover-crop each image to 1280x720, apply a slow zoom, draw captions with Pillow, crossfade scenes, mix ducked background audio.
5. **Export**: write `outputs/<job_id>/video.mp4` (H.264/AAC, 24 fps, 20-40 s).

## AI / Models / Libraries Used

| Component                   | Used for                    | Notes                                                                     |
| --------------------------- | --------------------------- | ------------------------------------------------------------------------- |
| Template engine (built in)  | Default script and captions | Deterministic, offline                                                    |
| Anthropic API (optional)    | AI script mode              | Receives only the form fields, no images; output is fact-checked          |
| edge-tts / gTTS             | Voice-over                  | Network required; app continues without it                                |
| FastAPI + Uvicorn           | Web backend                 |                                                                           |
| MoviePy 2.x, Pillow, FFmpeg | Video, overlays, encoding   |                                                                           |
| Background audio            | Music bed                   | `assets/audio/` (source and licence listed in `assets/audio/LICENSE.txt`) |
| Inter font                  | Caption text                | SIL OFL                                                                   |

### How AI output is checked

Every number, price and proper noun in the generated script must appear in your input. If not, that script is discarded and the template version is used, and the UI shows a "Template fallback used" notice.

## Sample Data and Output

- Input: `sample_data/sample.json` + `sample_data/images/`
- Output: `samples/sample_output.mp4` (about 33 s, 3-BHK luxury apartment example)

## Project Structure

```
app/            FastAPI app, script generation, TTS, image + video pipeline, static UI
assets/         background audio, fonts
sample_data/    synthetic sample input and images
samples/        sample_output.mp4
tests/          pytest suite
```

## Tests

```bash
pytest -q
```

## Error Handling

| Situation                        | Behaviour                                         |
| -------------------------------- | ------------------------------------------------- |
| < 4 valid images                 | Clear message; generation blocked                 |
| > 8 images                       | First 8 used; user notified                       |
| Corrupt image                    | Skipped with warning                              |
| Missing optional field           | Line omitted, no blank text                       |
| TTS/network failure              | Video built without voice-over; warning shown     |
| LLM failure or failed fact check | Template script used                              |
| Render error                     | Friendly message in UI; details in `logs/app.log` |

## Limitations

- Jobs are held in memory (a restart clears history); outputs are deleted after 24 h.
- 16:9 only; vertical (9:16) export is a possible extension.
- Voice quality depends on the free TTS engines.
- Rendering is CPU-only; expect about 1 minute for a 6-image video.

## Possible Extensions

Vertical/Reels format, multiple languages, logo/brand colour options, agent photo and QR code on the CTA scene, queue with persistent storage.

## Licence

MIT (or as required by your submission). Check the licences of any bundled audio, fonts and images.
