# Engine 2: architecture, audit and migration plan

Status (updated): **Stages 1 and 2 are implemented. Stage 3 (hybrid) is implemented as code and previewed on the real ORIGINAL references (NOT approved). Stages 4, 5, 7 and 8 are partly done (see the table). Stage 9 onward needs Cloudflare drawings and the owner's approval.** Nothing in engine 2 is used by production. `ART_MODE` stays off. Nothing is published.

## Stage 1: repository audit (22 Nov 2026, from the live repository)

### Production paths (unchanged)

The workflow `horror-story.yml` runs `main.py`. It is started by cron-job.org at 7:00 AM, 10:00 AM and 5:00 PM IST. Backup clocks run at 05:45 and 11:15 UTC.

`main.py` (14.7k lines) and `extras.py` (9k lines) hold the story engine and all publishing:
- Story writing (2 AM run).
- TTS.
- YouTube, Facebook, podcast and Telegram.
- Comments, history and the website.

The video picture side has four routes, all existing:

| Route | Switch | What it uses |
|---|---|---|
| Classic (default) | `ANIM_MODE` empty | **Cloudflare scene pictures every story** (`cf_request` → `_cf_request_all`, `flux-2-klein-4b`, 1024×576), thumbnails, Ken-Burns style compositing |
| V8 characters | `ANIM_MODE=character` | `characters.py`, `compositor.py`, `silhouette.py`, `manifest.py` |
| V1.1 cartoon engine | `ANIM_MODE=cartoon` | `story_engine.py`, `scene_planner.py`, `animation_renderer.py`, `cartoon_rig.py` (code-drawn characters), `environment_animation.py`, `location_library.py`, `cinematic_camera.py`, `lip_sync.py`, the three assistants |
| 2.5D cut-out | `ART_MODE=cutout` (off) | `cutout_assets.py`, `puppet_builder.py`, `assembly_qa.py`, `cutout_rig.py`; only puppets that passed the gate |

**Why the free Cloudflare quota was gone in the morning:** the classic production route draws every story's scene pictures and thumbnails on the same Cloudflare account. Engine 2 removes character-image generation from rendering; the production route is not changed.

### Character assets that exist

Everything is in `assets/cartoon_parts/<key>/` and comes from the art_test of 21 Nov:
- Hari, Saraswati, Petni, Taranath, Kishori and Madhusundari each have the original Cloudflare reference (`body.png` cut out, `body_src.png` untouched).
- They also have the first-version pieces and rigs. These are rejected by the gate and never used.

Other related files:
- `index.json` holds the registry.
- `sheet/` holds char_sheet progress. Hari has 0 of 7 pictures, because of the HTTP 429 limit.
- `assets/cartoon_cast.json` holds the designer's records.

### Test modes

All test modes run before the daily jobs. None of them answers, posts, or changes production history:
- `pilot`, `anim_test`, `story_test`, `art_test`
- `full_test` (a dry run that is not committed)
- `char_sheet`
- `library_sync` (new)

### Secrets and variables

Only names were read; no values. Relevant here:
- Secrets: `CF_ACCOUNT_ID`, `CF_API_TOKEN` (one account by design), `TELEGRAM_*`, `GEMINI_*`.
- Variables: `ANIM_MODE`, `ART_MODE`, `ART_MAX_IMAGES`.

### Integration points engine 2 will use later (not yet)

- `story_engine.engine_clip`: per scene, the characters.
- `scene_planner.plan_from_story`: actions.
- `animation_renderer.render`: drawing.
- `lip_sync`: mouth timing from the real audio.

Engine 2 will plug in behind a new feature flag `ENGINE2=on`. The default is off and it is read nowhere yet.

## Stage 2: the permanent Character Asset Library (implemented)

The code is in `engine2/library.py`. The data is in `assets/character_library/`, committed by the workflow.

```
assets/character_library/
  APPROVALS.json            only the OWNER edits this file; the code never writes an approval
  library_report.json
  hari/manifest.json        character_id, asset_version, original_reference, approval_status, body_proportions,
                            layer_order, joint_coordinates, anchor_points, available_poses, available_parts,
                            available_expressions, missing_expressions, missing_assets, validation_status, integrity
  hari/v1/reference/original.png, original_src.png
  hari/v1/poses/{front,side,stand,sit,talk,point,walk1..4}.png     (method B: complete poses)
  hari/v1/parts/<part>.png + rig.json                            (method A: cut-out, from the FRONT drawing)
  hari/v1/props/prop_N.png
  hari/v1/version.json      per asset: sha256, status, problems, provider, model, source, time
  hari/rejected/            replaced candidates are moved here and never deleted
```

**Asset statuses** are kept apart:

| Status | Who gives it |
|---|---|
| `GENERATED` | The file exists |
| `TECHNICALLY_VALID` / `VISUAL_REVIEW_REQUIRED` | The best the code can give |
| `USER_APPROVED` | Only from `APPROVALS.json` |
| `REJECTED` | A technical failure, or the owner |

**Rules:**
- Nothing is overwritten.
- A changed file opens a new version.
- An approved version is immutable. A later candidate never replaces it in videos.
- Integrity is checked with sha256, and a damaged approved version blocks use.
- `render_assets()` returns assets only for an owner-approved, complete, undamaged version. It never generates an image.

**Creating assets** (optional, once per character) uses `char_sheet`, the only place that calls Cloudflare:
- The original reference is the identity for every picture.
- Every passed picture is saved and pushed at once.
- HTTP 429 stops the run cleanly, and the next run resumes only the missing pictures.
- `character=Hari` limits a run to one character.
- After each run the library is synced.

## Stages 3 to 12: status

| Stage | Done | Still missing (honestly) |
|---|---|---|
| 3. Hybrid animation | `engine2/hybrid.py`: method A (cut-out, `cutout_rig`) and method B (`engine2/fullpose.py`, complete drawings: stand, talk, point, sit, 4-frame walk). Per-frame choice: complex actions use the drawings, the rest the rig. An action table reports what is MISSING. | Approved assets. Drawings for running, falling, fighting, waving, namaste and fear do not exist yet. |
| 4. Facial | Mouth from the real audio (`lip_sync`, amplitude-based visemes: a documented approximation, not Bengali phonemes). Blinking on the character's own face. | All expressions except neutral (each needs its own approved drawing). |
| 5. Scene and camera | The existing scene engine is reused: backgrounds, layered environment, fog, dust, flicker, the camera (wide, medium, close, pans, focus on speaker), and the seat rule. | Reusable approved painted backgrounds (plates) for every location. |
| 6. Story integration | The existing pipeline: story lines → the three assistants → scene planner → renderer, with hybrid characters (in `hybrid_test`). | Production integration behind `HYBRID_2D_MODE` (not added: nothing is approved). |
| 7. Rendering | 1280×720, 24 fps, H.264 yuv420p, AAC (the existing renderer + mux). Per-shot chunks with a cache key. | Subtitles; a whole-story resume across runs. |
| 8. QA | `engine2/videoqa.py` (resolution, fps, codecs, audio/picture length, black frames), the assembled gate, the library integrity check. | Visual QA = the owner. |
| 9 to 12 | `hybrid_test` mode (Telegram + artifacts). | Hari's char_sheet drawings, then the owner's approval, then Saraswati and Kishori, then a full story test (not published). |

## Rollback

Engine 2 is read by no production path. To remove it:
1. Delete the `engine2/` folder.
2. Delete the functions `char_sheet_run`, `library_sync_run` and `hybrid_test_run` and their `MODE` lines in `main.py`, and the `elif d.get("hybrid")` branch in `animation_renderer.py`.
3. Remove `assets/character_library` from the workflow's commit list.

`ANIM_MODE`, `ART_MODE` and every production route behave exactly as before. The library data (`assets/character_library/`) can be kept; nothing reads it.
