# 🎬 AI Property Video Generator — Implementation Plan

## Project Understanding

A **single-page web app** that takes property details + 4–8 images and generates a 20–40 second promotional MP4 video with:
- Text overlays (captions), transitions, Ken Burns zoom, background audio
- Optional voice-over (edge-tts → gTTS fallback)
- Optional AI script generation (Anthropic API → template fallback)
- Job-based async rendering with live progress polling

**Stack:** Python 3.11, FastAPI, Vanilla HTML/JS/CSS, MoviePy 2.x, Pillow, FFmpeg (imageio-ffmpeg), edge-tts/gTTS, Anthropic API (optional)

---

## Architecture Overview

```
Browser (HTML/JS/CSS)
    │  POST /api/generate (multipart form)
    │  GET  /api/jobs/{id} (polling, 1s)
    ▼
FastAPI (main.py)
    ├── schemas.py       → Pydantic input validation
    ├── jobs.py          → In-memory job store + background thread runner
    ├── script_gen.py    → Template / LLM script builder + fact-checker
    ├── tts.py           → edge-tts → gTTS → silent fallback
    ├── images.py        → Load, validate, 16:9 crop, Ken Burns frames
    ├── overlays.py      → Pillow caption bar rendering
    └── video.py         → Scene assembly, audio mixing, MP4 export
```

---

## Phase-by-Phase Plan

---

### Phase 1 — Project Skeleton & Health Check
**Goal:** Runnable repo with correct structure, FastAPI serving static files, `GET /api/health`.

#### Tasks
1. Create all directories: `app/`, `app/static/`, `assets/audio/`, `assets/fonts/`, `sample_data/images/`, `samples/`, `outputs/`, `tests/`, `logs/`
2. Write `requirements.txt` with pinned versions:
   - `fastapi`, `uvicorn[standard]`, `python-multipart`
   - `moviepy>=2.0`, `Pillow`, `imageio-ffmpeg`
   - `edge-tts`, `gTTS`
   - `anthropic`, `python-dotenv`
   - `pytest`, `pytest-asyncio`, `httpx`
3. Write `app/main.py`:
   - FastAPI app instance
   - Mount `app/static/` as StaticFiles at `/`
   - `GET /api/health` → `{"status": "ok"}`
   - Serve `index.html` on the root `/` route
4. Write a minimal `app/static/index.html` placeholder (just "AI Video Generator")
5. Write `.env.example` with `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL`, `ENABLE_TTS`, `MAX_UPLOAD_MB`
6. Write `.gitignore` (outputs/, .env, logs/, __pycache__, .venv)

**✅ Verification:** `uvicorn app.main:app --reload` runs on port 8000, `/api/health` returns 200.

---

### Phase 2 — Pydantic Schemas & Input Validation
**Goal:** Rock-solid server-side validation with field-level error responses.

#### Tasks
1. Write `app/schemas.py`:
   - `PropertyInput` Pydantic model:
     - `property_name`: str, 2–80 chars
     - `location`: str, 2–120 chars
     - `price`: str (non-empty)
     - `property_type`: `Literal["Apartment", "Villa", "House", "Plot", "Commercial", "Other"]`
     - `bedrooms`: `Optional[str]`
     - `area`: `Optional[str]`
     - `key_features`: `List[str]`, min 3, max 8 items
     - `contact_cta`: str (non-empty)
     - `voiceover_enabled`: bool, default True
     - `script_mode`: `Literal["template", "ai"]`, default "template"
   - Image validation helper: checks MIME type (JPG/PNG/WebP), size ≤ 8 MB
   - `JobStatus` enum: `queued | scripting | narrating | rendering | done | error`
   - `JobResponse` model: `{job_id, status, progress, message, warnings}`
2. Add `POST /api/generate` stub in `main.py` that runs validation and returns `{job_id: "test"}` placeholder
3. Add `GET /api/jobs/{job_id}` stub returning mock status

**✅ Verification:** Pytest tests for valid payload, missing required fields, invalid image count.

---

### Phase 3 — Frontend UI (Design Spec Implementation)
**Goal:** Full UI matching the black/orange design spec, wired to backend with mocked responses.

#### Design Tokens
| Token | Value |
|---|---|
| Background | `#0B0B0B` |
| Surface | `#151515` |
| Border | `#262626` |
| Text | `#F5F5F5` |
| Muted | `#9A9A9A` |
| Accent Orange | `#FF6A1A` |
| Accent Hover | `#FF8442` |
| Error | `#FF4D4D` |
| Font | Inter (Google Fonts) → system-ui fallback |

#### Tasks
1. Write `app/static/styles.css`:
   - CSS custom properties for all design tokens
   - Base reset, body, Inter font import
   - Card styles (1px border, 12px radius, no shadows)
   - Form inputs: dark fill, orange focus ring
   - Buttons: solid orange primary, outlined secondary
   - Progress bar, toast notification
   - Mobile responsive (<640px)
2. Write `app/static/index.html`:
   - Header with wordmark
   - **Card 1 — Details**: property name, location, price, type dropdown, bedrooms (optional), area (optional), key features (textarea/chips), contact CTA, voice-over toggle, script mode toggle
   - **Card 2 — Images**: drag-and-drop zone, thumbnail grid, remove (×), reorder by drag
   - **"Load sample data"** button
   - Full-width orange **"Generate video"** button
   - Progress card (hidden initially): stage text + animated progress bar
   - Result card (hidden initially): `<video controls>`, Download MP4 button, script display
   - Inline error display under each field
3. Write `app/static/app.js`:
   - Form validation (client-side mirrors server-side)
   - Image drag-drop zone: FileReader previews, reorder, remove
   - `loadSampleData()`: fetch `sample_data/sample.json` → populate form
   - `generateVideo()`: build FormData, POST `/api/generate`, handle errors
   - `pollJob(jobId)`: setInterval 1s → `GET /api/jobs/{id}` → update progress bar and stage text
   - On completion: show video player, download button, script JSON
   - On error: friendly toast + re-enable form
4. Add sample data file `sample_data/sample.json` with synthetic property data

**✅ Verification:** UI matches design spec; form shows inline errors; progress card and result card toggle correctly with mocked API.

---

### Phase 4 — Script Generation (Template + LLM + Fact-Check)
**Goal:** Produce valid scene JSON from inputs using templates, with optional LLM with fallback.

#### Scene Structure
```json
{
  "scenes": [
    {"type": "title",   "image_index": 0, "caption": "...", "voiceover": "..."},
    {"type": "feature", "image_index": 1, "caption": "...", "voiceover": "..."},
    {"type": "details", "image_index": N, "caption": "...", "voiceover": "..."},
    {"type": "cta",     "image_index": M, "caption": "...", "voiceover": "..."}
  ]
}
```

#### Tasks
1. Write `app/script_gen.py`:

   **Template mode:**
   - Title scene: `"{property_name} | {location}"`
   - Feature scenes (one per feature, 3–5 selected): `"✦ {feature}"`, ≤8 words
   - Details scene: compose from available fields (price always shown; bedrooms/area only if provided)
   - CTA scene: `contact_cta` text split to ≤8 words/line
   - Voice-over: sentence-per-scene, ≤25 words, skip optional field mentions if not supplied

   **AI mode (optional):**
   - Build prompt with only the input fields (NO images)
   - Require JSON output matching scene structure schema
   - Parse and validate JSON
   - **Fact-check**: extract all numbers, prices (regex), proper nouns; every one must appear in original input
   - On failure → log reason → fall back to template → set `used_template_fallback=True`

2. `generate_script(inputs, mode) -> (scene_list, warnings)` function
3. Caption line-wrap: enforce ≤8 words per line (split on word boundary)
4. Voice-over truncation: enforce ≤25 words (trim, add "…" if needed)

**✅ Verification:** Pytest — invented fact causes fallback; all scene types present; captions within word limits.

---

### Phase 5 — Image Processing (Crop + Ken Burns)
**Goal:** Validated, cover-cropped 1280×720 images with Ken Burns animation frames.

#### Tasks
1. Write `app/images.py`:
   - `validate_image(file_bytes) -> PIL.Image | None`: open with Pillow; catch all exceptions; return None if corrupt
   - `cover_crop(img, width=1280, height=720) -> PIL.Image`: resize to fill 16:9 without stretching, then center-crop (no black bars)
   - `generate_ken_burns_frames(img, duration_s, fps=24, zoom_start=1.0, zoom_end=1.05) -> List[PIL.Image]`:
     - Gentle zoom-in over the scene duration
     - Crop from center at each frame, scaled from zoom_start to zoom_end
     - Returns list of PIL frames
   - `load_and_validate_images(file_list) -> (valid_images, warnings)`:
     - Skip corrupt → add to warnings
     - Accept first 8 if >8 → add warning
     - Raise error if <4 valid after filtering

**✅ Verification:** Unit test — cover crop produces exactly 1280×720; Ken Burns first/last frames differ; corrupt bytes return None with no exception raised.

---

### Phase 6 — Caption Overlays (Pillow Rendering)
**Goal:** Readable caption bar rendered onto each video frame.

#### Tasks
1. Write `app/overlays.py`:
   - `draw_caption_bar(frame_img, text, font_path, font_size=36) -> PIL.Image`:
     - Semi-transparent dark bar at bottom ~20% height
     - White text centered horizontally
     - 3px orange accent line at top of bar
     - Handle multi-line text (≤8 words/line enforced in script_gen; overlays just wraps and renders)
     - Must remain readable on bright images (semi-transparent dark overlay ensures contrast)
   - Load Inter font from `assets/fonts/`; fallback to Pillow default if missing
   - `composite_frames(ken_burns_frames, caption_text, font_path) -> List[np.ndarray]`:
     - Apply `draw_caption_bar` to each frame
     - Return as numpy arrays ready for MoviePy

**✅ Verification:** Render one still frame per scene type (title/feature/details/CTA) and visually verify readability on both dark and bright test images.

---

### Phase 7 — Voice-Over & Audio (TTS + Background Music)
**Goal:** Per-scene audio clips + royalty-free background music mixed at 15% volume.

#### Tasks
1. Write `app/tts.py`:
   - `synthesize_scene(text, output_path, lang="en") -> float | None`:
     - Try `edge-tts` (async call, save to file, measure duration with moviepy or mutagen)
     - On network failure → try `gTTS` → save → measure duration
     - On both failures → return None (silent scene)
     - Add warning to job warnings list
   - `get_audio_duration(path) -> float`: use moviepy AudioFileClip
   - Async-aware: wrap edge-tts `asyncio.run()` properly within sync thread context

2. Procure/generate background audio:
   - Source a CC0 royalty-free ambient/soft piano loop (e.g., from Pixabay, Freesound)
   - OR generate a simple sine-wave ambient tone programmatically using numpy + scipy/soundfile
   - Place in `assets/audio/background.mp3`
   - Document source/licence in `assets/audio/LICENSE.txt`

3. Audio timing logic (in `video.py`):
   - If TTS clip > scene duration → extend scene up to 6s
   - If still longer → trim voiceover text (handled in script_gen) or trim audio
   - Duck background music to ~15% under voice-over; full 15% otherwise
   - Fade background audio out in last 1.5s

**✅ Verification:** Run with network blocked → video produced with warning; audio durations measured correctly; mixing produces no clipping.

---

### Phase 8 — Video Assembly & Export
**Goal:** Full pipeline: frames → scenes → crossfades → audio mix → H.264/AAC MP4.

#### Tasks
1. Write `app/video.py`:
   - `build_scene_clip(frames, voiceover_path, caption_already_composited=True) -> moviepy.VideoClip`:
     - Create ImageSequenceClip from frames (24 fps)
     - Attach voiceover AudioFileClip if path provided
   - `assemble_video(scenes, script, image_paths, audio_path, output_path, job_cb) -> None`:
     - For each scene: generate Ken Burns frames → composite captions → build VideoClip
     - Scale scene durations so total is 20–40s
     - Apply 0.5s crossfade between scenes (`moviepy.video.fx.CrossFadeIn`)
     - Concat all scenes
     - Load background audio loop → loop/trim to video length → duck to 15%
     - Mix background + voiceover tracks
     - Export: `write_videofile(output_path, fps=24, codec="libx264", audio_codec="aac")`
     - Call `job_cb(progress, stage)` at key milestones

2. Validate output:
   - Must be 1280×720, 24fps, H.264 video + AAC audio
   - Duration must be 20–40s

**✅ Verification:** `ffprobe outputs/{id}/video.mp4` shows correct codec, resolution, fps, and duration.

---

### Phase 9 — Jobs System & API Completion
**Goal:** Full async job lifecycle with background rendering, status polling, and 24h cleanup.

#### Tasks
1. Write `app/jobs.py`:
   - `Job` dataclass: `id, status, progress, message, warnings, created_at, output_path`
   - `JobStore`: in-memory dict `{job_id: Job}`
   - `create_job() -> str`: UUID4 job ID
   - `update_job(id, **fields)`: thread-safe update
   - `get_job(id) -> Job | None`
   - `cleanup_old_jobs()`: delete jobs + output dirs older than 24h
   - `run_job(job_id, inputs, image_bytes_list)`: full pipeline:
     1. status=scripting → `script_gen.generate_script()`
     2. status=narrating → `tts.synthesize_scene()` per scene
     3. status=rendering → `video.assemble_video()` (with progress callback)
     4. status=done → set output_path
     5. On any exception → status=error, message=friendly string, log full traceback

2. Update `app/main.py`:
   - `POST /api/generate`: parse multipart form + images → validate → `create_job()` → `ThreadPoolExecutor.submit(run_job, ...)` → return `{job_id}`
   - `GET /api/jobs/{job_id}`: return job state
   - `GET /api/jobs/{job_id}/video`: serve the MP4 file (or 404 if not done)
   - Startup event: `cleanup_old_jobs()` on app start
   - Background cleanup: schedule cleanup every hour via asyncio task

3. Update `app.js` polling:
   - On `done`: set `<video src>` to `/api/jobs/{id}/video`, show download button
   - On `error`: show error message, re-enable form
   - On `warnings` array: show warning notices above video player

**✅ Verification:** Progress bar moves through all stages; forced error (no images) shows friendly message; cleanup removes old output dirs.

---

### Phase 10 — Hardening, Tests & Sample Output
**Goal:** All edge cases handled, full test suite passing, sample output committed.

#### Tasks
1. Edge case hardening (FR-1, FR-6):
   - <4 images: block generation, clear UI message
   - >8 images: use first 8, warn
   - Corrupt image: skip, warn, continue if ≥4 valid remain
   - Missing optional fields: omit gracefully (no "None" text)
   - Missing FFmpeg: friendly error at startup
   - TTS network failure: continue without voice-over, warn
   - LLM failure: template fallback, show notice
   - Disk write failure: friendly error, log details

2. Write `tests/`:
   - `test_validation.py`: valid/invalid payload, image count rules
   - `test_script_gen.py`: template output schema valid; invented fact causes fallback
   - `test_images.py`: cover_crop returns 1280×720; corrupt bytes handled
   - `test_e2e.py`: `POST /api/generate` with sample data → poll until done → verify MP4 exists

3. Logging:
   - Configure `logging` to write to `logs/app.log` with rotation
   - Log all errors at ERROR level, pipeline milestones at INFO

4. Generate `samples/sample_output.mp4`:
   - Run full pipeline with `sample_data/` input
   - Commit output

5. Final README:
   - Confirm setup steps work from fresh clone
   - List every model/API/library used
   - No secrets anywhere in repo

**✅ Verification:** All tests pass (`pytest -q`); fresh clone → video in <10 min; no API keys in repo.

---

## Dependency Graph (Phase Order)

```
Phase 1 (Skeleton)
    └─→ Phase 2 (Schemas)
            ├─→ Phase 3 (UI)       ← can partially parallelize with 4
            └─→ Phase 4 (Script)
                    ├─→ Phase 5 (Images)
                    │       └─→ Phase 6 (Overlays)
                    └─→ Phase 7 (TTS/Audio)
                            └─→ Phase 8 (Video Assembly)  ← needs 5, 6, 7
                                    └─→ Phase 9 (Jobs API)
                                            └─→ Phase 10 (Hardening)
```

---

## Key Risk Areas & Mitigations

| Risk | Mitigation |
|---|---|
| MoviePy 2.x API changes from 1.x | Pin `moviepy>=2.0,<3.0`; test clip creation early in Phase 5 |
| FFmpeg not found | Use `imageio-ffmpeg` to bundle; catch at startup with clear error |
| edge-tts async in thread | Wrap with `asyncio.run()` in a dedicated thread; isolate event loop |
| Ken Burns perf (too slow) | Pre-render all frames to disk before MoviePy assembly; limit to 6-8 frames/sec during KenBurns |
| ImageMagick conflict | Pillow-only for text overlays (as spec requires); explicitly set `IMAGEMAGICK_BINARY=None` |
| LLM hallucination in fact-check | Strict regex extraction + whitelist matching; any miss = full template fallback |

---

## File Delivery Checklist

- [ ] `requirements.txt`
- [ ] `.env.example`
- [ ] `.gitignore`
- [ ] `app/main.py`
- [ ] `app/schemas.py`
- [ ] `app/jobs.py`
- [ ] `app/script_gen.py`
- [ ] `app/tts.py`
- [ ] `app/images.py`
- [ ] `app/overlays.py`
- [ ] `app/video.py`
- [ ] `app/static/index.html`
- [ ] `app/static/styles.css`
- [ ] `app/static/app.js`
- [ ] `assets/audio/background.mp3` + `LICENSE.txt`
- [ ] `assets/fonts/Inter-Regular.ttf` (+ Bold)
- [ ] `sample_data/sample.json` + `sample_data/images/` (4-8 CC0 photos)
- [ ] `samples/sample_output.mp4`
- [ ] `tests/test_validation.py`
- [ ] `tests/test_script_gen.py`
- [ ] `tests/test_images.py`
- [ ] `tests/test_e2e.py`
- [ ] `README.md` (finalised)
