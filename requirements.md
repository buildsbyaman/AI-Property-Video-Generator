# requirements.md: AI Property Video Generator (Web)

## 1. Goal
A web app where a user enters property details and uploads 4-8 images, then gets a
20-40 second MP4 promotional video (title scene, feature scenes, enquiry CTA) with
captions, transitions, background audio and optional voice-over. No manual video editing.

## 2. Scope
- Web UI only. No CLI entry point for end users (a small `scripts/` dir for dev/test is fine).
- Prototype quality, not enterprise. Prioritise: working end to end, graceful errors, clear README.

## 3. Tech Stack (fixed, do not substitute without a reason in the README)
- Backend: Python 3.11+, FastAPI, Uvicorn
- Frontend: single-page HTML + vanilla JS + CSS served by FastAPI (no build step, no framework)
- Video: MoviePy 2.x + Pillow (render text overlays with Pillow, NOT ImageMagick) + FFmpeg (via imageio-ffmpeg)
- Voice-over: edge-tts (free, no key) with gTTS as fallback; narration is optional
- Script generation: template logic by default; optional LLM mode (Anthropic API via `ANTHROPIC_API_KEY`)
  that falls back to templates if no key or if validation fails
- Audio: one royalty-free/CC0 loop in `assets/audio/` OR a generated soft ambient tone; document the source
- Config: `.env` loaded with python-dotenv; ship `.env.example`, never real keys

## 4. Inputs
| Field | Required | Rules |
|---|---|---|
| Property name | yes | 2-80 chars |
| Location | yes | 2-120 chars |
| Price | yes | free text, e.g. "₹85 Lakh" or "$450,000" |
| Property type | yes | dropdown: Apartment, Villa, House, Plot, Commercial, Other |
| Bedrooms/config | no | e.g. "2 BHK" |
| Area | no | e.g. "1,050 sq ft" |
| Key features | yes | 3-8 items, one per line or chips |
| Contact / CTA text | yes | e.g. "Call 98xxxxxx or visit example.com" |
| Images | yes | 4-8 files, JPG/PNG/WebP, each <= 8 MB |
| Voice-over | no | toggle on/off (default on) |
| Script mode | no | Template (default) or AI |

Include a **"Load sample data"** button that fills the form and uses images from `sample_data/images/`.

## 5. Functional Requirements

### FR-1 Form and validation
- Client-side and server-side validation. Return field-level errors as JSON `{field, message}`.
- Fewer than 4 images -> clear message, no crash. More than 8 -> use the first 8 and tell the user.
- Corrupt/unreadable image -> skip it, warn the user, continue if >= 4 valid images remain.
- Missing optional fields -> omit that line from script and captions (never print "None" or blank labels).

### FR-2 Script and caption generation
- Output JSON: `{ scenes: [{type, image_index, caption, voiceover}] }`.
- Scene plan: 1 title, 3-5 feature scenes, 1 details scene (price/type/area), 1 CTA.
- **Only use facts supplied in the input.** No invented amenities, distances, ROI, or "near metro" claims.
- Template mode: deterministic sentence templates per scene type.
- AI mode: send only the input fields in the prompt, require JSON output, then run **fact check**:
  every number, price, and proper noun in the output must appear in the input; otherwise
  discard and fall back to templates. Show "Template fallback used" in the UI when this happens.
- Captions <= 8 words per line; voice-over <= 25 words per scene.

### FR-3 Video assembly
- 1280x720, 24 fps, H.264 + AAC, MP4.
- Each scene 3-5 s; total 20-40 s (scale scene length to fit).
- Images are cover-cropped to 16:9 (no stretching, no black bars) with a gentle Ken Burns zoom.
- Text overlay: caption on a semi-transparent dark bar, white text, orange accent line; must stay readable on bright images.
- Title scene shows name + location; details scene shows price/type/area; CTA scene shows contact text.
- 0.5 s crossfade between scenes.
- Background audio at ~15% volume, ducked under voice-over; fade out at the end.
- Voice-over audio is timed per scene; if narration is longer than the scene, extend the scene (up to 6 s) or trim the text.

### FR-4 Jobs and progress
- `POST /api/generate` returns `{job_id}` immediately; rendering runs in a background thread/task.
- `GET /api/jobs/{id}` returns `{status: queued|scripting|narrating|rendering|done|error, progress: 0-100, message, warnings[]}`.
- UI polls every 1 s and shows a progress bar and stage text.

### FR-5 Preview and export
- On completion: in-page `<video controls>` preview, "Download MP4" button, and the generated script/captions shown beneath.
- Files saved to `outputs/{job_id}/video.mp4`. Old jobs auto-clean after 24 h (or on startup).

### FR-6 Error handling
- Every failure path returns a human-readable message in the UI (no stack traces, no blank screen).
- Cover: missing FFmpeg, TTS/network failure (continue without voice-over and warn), LLM failure (fall back to template), disk write failure, oversized or wrong-type uploads.
- Log full details server-side to `logs/app.log`.

## 6. Non-Functional Requirements
- Render a 6-image video in under 90 s on a normal laptop (no GPU).
- Works offline in Template mode with voice-over off.
- No secrets or real personal data in the repo. Sample data is synthetic.
- Code is split into modules (see section 8), with type hints and short docstrings.
- Minimum tests (pytest): input validation, script fact-check, image cropping, one end-to-end render with sample data.

## 7. UI / Design Spec (minimal, black + orange)
- Palette: background `#0B0B0B`, surface `#151515`, border `#262626`, text `#F5F5F5`, muted `#9A9A9A`, accent orange `#FF6A1A`, accent hover `#FF8442`, error `#FF4D4D`.
- Font: Inter (system-ui fallback). Generous spacing, 12px radius on cards, 1px borders, no shadows or gradients.
- Layout: single centred column (max 960px). Header with small wordmark, then two cards: **1. Details** and **2. Images**, then a full-width orange "Generate video" button.
- After submit: the form collapses to a progress card, then the result card (video preview + download + script).
- Image upload: drag-and-drop zone with thumbnails, reorder by drag, remove with an x.
- Primary buttons are solid orange with black text; secondary buttons are outlined. Inputs have a dark fill with an orange focus ring.
- Inline field errors in red under the field; toasts only for global errors.
- Mobile responsive (single column under 640px). No icon packs, no animations beyond the progress bar and a 150 ms hover transition.

## 8. Project Structure
```
property-video-generator/
├── app/
│   ├── main.py            # FastAPI app, routes, static serving
│   ├── schemas.py         # Pydantic models + validation
│   ├── jobs.py            # in-memory job store, background runner, cleanup
│   ├── script_gen.py      # template + optional LLM + fact check
│   ├── tts.py             # edge-tts / gTTS wrapper with fallback
│   ├── images.py          # load, validate, cover-crop, Ken Burns frames
│   ├── overlays.py        # Pillow text/caption rendering
│   ├── video.py           # scene assembly, audio mix, MP4 export
│   └── static/            # index.html, styles.css, app.js
├── assets/audio/          # royalty-free background loop
├── assets/fonts/          # Inter (OFL) for Pillow
├── sample_data/           # sample.json + images/ (4-8 synthetic or CC0 photos)
├── samples/               # sample_output.mp4 (committed)
├── outputs/               # generated, git-ignored
├── tests/
├── .env.example
├── requirements.txt
└── README.md
```

## 9. Build Plan for the Agent (do in order; verify each before moving on)

**Phase 1: Skeleton**
Create the project, `requirements.txt`, FastAPI app serving a static page and `GET /api/health`.
*Check:* `uvicorn app.main:app` runs and the page loads.

**Phase 2: Schemas and validation**
Pydantic models for all inputs, upload checks (type, size, count), field-level error format.
*Check:* tests for valid/invalid payloads pass.

**Phase 3: UI**
Build the form, image dropzone, "Load sample data", and result/progress cards to the design spec. Wire to the API with mocked responses first.
*Check:* the UI matches section 7 and validation messages show inline.

**Phase 4: Script generation**
Template generator, then optional LLM mode, then fact check and fallback.
*Check:* tests prove an invented fact causes template fallback; output JSON schema is valid.

**Phase 5: Images and overlays**
Cover-crop to 1280x720, Ken Burns, Pillow caption bar with wrapped text.
*Check:* render one still frame per scene type and eyeball readability on light and dark images.

**Phase 6: Voice-over and audio**
edge-tts per scene with gTTS fallback; measure durations; mix with ducked background audio.
*Check:* a run with the network blocked still produces a video and a warning.

**Phase 7: Video assembly**
Combine scenes with crossfades, enforce the 20-40 s total, export H.264/AAC MP4.
*Check:* ffprobe shows 1280x720, 24 fps, duration in range, and the file plays in a browser.

**Phase 8: Jobs and progress**
Background runner, status endpoint, UI polling, cleanup task.
*Check:* the progress bar moves through all stages; a forced error shows a friendly message.

**Phase 9: Hardening and tests**
Edge cases from FR-1 and FR-6, logging, end-to-end test.
*Check:* all tests pass; manual run with 3 images, a corrupt image, and a missing optional field behaves gracefully.

**Phase 10: Deliverables**
Generate and commit `samples/sample_output.mp4`, finalise the README, confirm no secrets are committed.
*Check:* a fresh clone follows the README and produces a video in under 10 minutes.

## 10. Acceptance Criteria (Definition of Done)
- [ ] Fresh clone + README steps -> app runs on `http://localhost:8000`
- [ ] "Load sample data" -> Generate -> playable MP4 with title, 3+ feature scenes, details, CTA
- [ ] Every caption and voice-over line traces back to supplied input
- [ ] Missing images, a corrupt file, and TTS/LLM failures never crash the app
- [ ] UI is black/orange, minimal, and readable on mobile
- [ ] `samples/sample_output.mp4` committed; README lists every model/API/library used
- [ ] No API keys, passwords, or real personal data anywhere in the repo