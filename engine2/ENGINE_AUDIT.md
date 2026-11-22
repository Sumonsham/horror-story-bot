# Engine 2 audit (23 Nov 2026, from the live repository at commit d8eef2c)

All findings below come from reading the code and running it in a sandbox (Python 3, OpenCV 5, ffmpeg 6.1, Node 22).
"Verified" = executed here. "Read" = read in the code, not executed.

## A. Working components (verified)

| Component | File | Evidence |
|---|---|---|
| Character asset library, versioned, sha256, owner-only approvals | `engine2/library.py` | `tests/test_engine2_library.py` passes; `render_assets()` returns nothing without an owner approval |
| Hari's skeletal rig (Rigby2D AutoRig, weighted arm/leg meshes, IK feet) | `assets/character_rigs/hari/`, `engine2/rigby/*` | `proof.run('hari')`: rest pose differs from the drawing in 383 of 152,549 px (0.25 %); planted-foot slide 0.014 px/frame |
| CPU rasteriser for the vendored Rigby2D runtime | `engine2/rigby/raster.py` | renders 720p frames, no GPU |
| Arm-lift test | `engine2/rigby/armlift.py` | runs; it FAILS the rig at 30 deg and above (see D) - the test does its job |
| Video QA (resolution, fps, codecs, audio length, black frames) | `engine2/videoqa.py` | proof video passes: 1280x720, 24 fps, h264, yuv420p, aac |
| Pose-first artwork generation (manual, Hari only) | `engine2/posefirst.py`, mode `pose_art` | the 22 Nov run produced 6 pictures; 3 passed its checks |
| Scene engine reused for backgrounds | `location_library.py`, `environment_animation.py`, `cinematic_camera.py` | 7 locations; used by `proof.Stage` and the new render test |
| Complete-pose character (method B) | `engine2/fullpose.py` | read; needs RGBA drawings named stand/talk/point/sit/walk1-4 |

## B. Incomplete components

- **No approved master artwork.** The pose-first master failed its own check ("arms touch the body"). Segmentation of a new master (Stage 4) therefore cannot start.
- **No action-pose drawings** for sit, walk, listen, scared or talk. Only `arm45`, `arm90` and `point_index` passed the automatic check, and none of them is approved.
- **No expression drawings.** Every face is neutral.
- **Lip-sync:** Rhubarb (MIT) works on GitHub through `rig_test`. Without it, the fallback is loudness-based. Neither one is Bengali phoneme alignment.
- **Complete poses carry no face marks.** They get no mouth and no blink.
- **No production integration.** `HYBRID_2D_MODE` is read nowhere, which is intended.

## C. Duplicate implementations (left in place, documented)

| Purpose | Implementations |
|---|---|
| Code-drawn or cut-out characters | `cartoon_rig.py`, `cutout_rig.py`, `puppet_builder.py`, `characters.py`, `silhouette.py`, and engine 2 (`hybrid.py`, `fullpose.py`, `rigby/`) |
| Preview renderers | `engine2/preview.py` (hybrid_test) and `engine2/rigby/proof.py` (rig_test) |

Nothing was removed. The new MVP reuses `rigby/raster.py`, `rigby/face.py`, `rigby/armlift.py`, `videoqa.py`, `library.py` and the scene engine. It does not add another rig or another renderer.

## D. Broken or unsafe (verified)

1. **The rig's own animations lift an arm into the range the arm-lift test fails.** The rest lift is about 21 deg. The arm-lift test fails the right arm from 30 deg, and the left arm at 30 deg and from 60 deg. Measured maximum lifts of the far (left) arm:

   | Animation | Max lift |
   |---|---|
   | `talk` | 56 deg |
   | `indicate` | 80 deg |
   | `sit_talk` | 53 deg |
   | `open_palms` | 43 deg |
   | `walk` | 37 deg |

   The rig_test QA still reported "no problems", because it only counts pieces and areas. On the frames at 100 % the raised arm leaves the chest with a thin, pinched shoulder. The MVP now measures every rig pose and eases arms back to the safe limit (`mvp.clamp_arms`).
2. **Black fragment at the waist in the walk cycle.** A dark wedge shows at the front of the pelvis in several walk phases (`I_walk_cycle.png`). It is a layer/weight problem in the rig (pelvis and thigh tops). **Fixed on 23 Nov** at the source by `engine2/rigby/hipcap.py`: the hidden top of each trouser leg was a square, trouser-wide cut that included the pocket fold. Exposure went from 175 px to 0 in every walk phase.
3. **The pose_art hair check is a false alarm.** It failed `arm120` and `both_up` with "hair dE 58-65". The new region-by-region identity check measures hair dE 10-12 on the same pictures, and the hair is black in all of them. `arm120` is still a WRONG pose: the hand scratches the head instead of lifting the arm. `both_up` is plausible but unapproved.
4. **The scene engine's atmosphere needs a float frame.** `proof.Stage.finish` swallows the resulting exception, so the rig_test video never had fog or flicker. The MVP converts the frame first (`mvp._atmos`).

## E. Dependencies

There is no new dependency. The MVP uses numpy, OpenCV, ffmpeg and the vendored Rigby2D runtime, all of which are already installed by the workflow. Rhubarb is downloaded at run time, as `rig_test` already does. See `DEPENDENCIES.md`.

## F. Production risks

- **The daily pipeline is untouched.** Production never imports `engine2.mvp`. A test (`test_production_paths_never_import_the_mvp`) guards this.
- **Cloudflare:** the MVP never calls it.
- **The commit step** ("Remember this story") is skipped for the three new modes, so a test cannot change repository state.

## G. Workflow inputs

These modes existed before: `rig_test`, `hybrid_test`, `full_test`, `pose_art`, `char_sheet`, `library_sync`.

The MVP adds `engine_audit`, `asset_qa` and `render_test`. It does not add `render_test`-specific inputs. `character` is reused, and `RENDER_PREVIEW=1` (an environment value) gives a 360p/12 fps preview.

## H. Missing visual QA (now added)

| Check | Where |
|---|---|
| Identity check per region | `mvp.identity` |
| Cut-out sheet on a green background, so holes and halos show | `asset_qa` |
| Hand and shoulder close-ups at 200 % and 400 %, located on each drawing | `asset_qa` |
| Decision table per action | `render_test` |
| Contact sheet of every scene | `render_test` |
| Character-height consistency | `render_test` |

Visual approval stays with the owner.
