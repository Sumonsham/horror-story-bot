# Engine 2, rig track: Hari's skeletal 2D rig

Status: **a first proof for Hari only. NOT approved, and NOT used by any production video.** `ART_MODE` stays off,
and `HYBRID_2D_MODE` does not exist yet. Nothing is published. Saraswati and Kishori wait until the owner approves Hari.

## 1. Visual failure audit of the previous hybrid preview (root causes)

The diagnostics are in `work/rig_test/audit/`:
- `<name>_grid.png`: the old cut-out rig with part outlines and joint markers.
- `hari_point_arm_x2.5.png`: an enlarged arm.

| Visible defect | Exact source in the old code |
|---|---|
| Characters too small | `engine2/preview.py` used a fixed camera zoom of 1.45, so a character filled about 50 % of 720 px. Nothing measured or set the character's height. |
| Arm comes out of the middle of the chest when raised | The old `puppet_builder` cut the upper arm with a flat top. Its pivot `sh_n` sat inside the torso, with no shoulder cap and no shoulder seam. Rotating it shows the cut edge on the chest. |
| Elbow and shoulder look hinged and stiff | Every limb was two rigid pictures rotating about a point, with a painted disc over the joint. Nothing bends: there is no mesh and no weights. |
| Hands look generic or wrong | Each side had only one drawn hand (open). "Pointing" rotated that open hand. Wrist rotation did not exist. |
| Walk without weight | The gait rotated rigid thighs and shins. The amplitude was capped so the trouser pieces would not tear. There was no planted IK foot, no heel strike or toe-off, and the hip bob was too small. |
| Sitting | The thighs were "foreshortened" by shortening a rigid picture. The demo's stool was a few drawn lines, and the far leg crossed the near one. |
| Repetitive movement | The demos reused three code poses (`stand_talk`, `stand_point`, `sit_talk`). Listening used the same pose as talking. |

**Root cause:** the old system had no rig. There were no layered artwork, no bones, no bending meshes and no weights. It was rigid pictures cut by heuristics.

## 2. Tools evaluated (verified in this repository's sandbox where possible)

| Tool | Licence | What was verified | Used for |
|---|---|---|---|
| **Rigby2D** 0.6 (github.com/jaisurya-dev-art/rigby2d) | MIT OR Apache-2.0 | Cloned at the commit in `engine2/rigby/runtime/RIGBY2D_COMMIT`. The `rigby` CLI runs on Node 22 **without** npm packages for AutoRig, joint editing, `batch_edit`, `export` and `validate`. Its pure-Python runtime (from `runtimes/renpy`) loads the export and passes in-process. Its GPU `render` needs a desktop app or a GPU Chromium (or `--allow-software`), so it is not used: frames are drawn by our CPU rasteriser. The MCP server needs the desktop app or Claude Desktop, so it was not needed. | AutoRig (bones, weighted bending meshes, IK), "Bone only" joint moves, weight painting (`paintWeights`), animation keys, export, and the Python runtime |
| **Rhubarb Lip Sync** 1.14.0 | MIT | The official Linux release ran on a Bengali voice sample with the language-independent `phonetic` recogniser: 46 mouth cues in 8 s, in 1.4 s. | Mouth timing (shapes A-H, X) |
| **SAM 2** (facebookresearch/sam2) | Apache-2.0 (per its repository) | **Not run here.** The model download host is blocked in this sandbox. It runs on CPU (hiera-tiny), so a GitHub runner could use it. It only makes masks and never reconstructs hidden body parts. | Not needed for these flat-colour cartoons: separating along the drawn ink lines is pixel-exact. Kept as an option for painterly references. |
| **OpenToonz** | Modified BSD | A desktop application. It has a command-line renderer, but making poses needs an artist at the GUI. | Recommended only for an artist who draws complete poses by hand (frame-by-frame correction). Not part of the automatic pipeline. |
| **Inpainting** (OpenCV Telea / LaMa) | BSD / Apache-2.0 | Not used on purpose. | Hidden regions are continued only with a short strip of the part's **own colour** under the covering part (far arm behind the torso, wrist in the cuff, ankle in the hem, neck under the jaw). No anatomy is invented. A pose that needs more than this needs a new drawing. |

**The chosen combination for GitHub Actions** is Python, OpenCV, ffmpeg, the vendored Rigby2D Python runtime and Rhubarb (downloaded by `rig_test`). Node and the Rigby2D source are needed only to rebuild a rig, which happens once per character and is not done daily. Cloudflare is not used.

## 3. Pipeline

```
ORIGINAL reference (character library, untouched)
  -> engine2/rigprep.py          separation along the drawn ink lines, using a hand-checked
                                 assets/character_rigs/<id>/prep.json:
                                   seeds         which flat colour region is which part
                                   close         where a drawn line stops short
                                   pants split   along the crotch line, with the pelvis fading into the thighs
                                   joints        read off the drawing at 3-4x zoom
                                   extend        hidden own-colour strips
                                   line_owner    which part owns a line
                                   face          mouth and eye positions
                                 It also removes the ground shadow and checks lost pixels (0 = every drawn pixel
                                 is in a layer). Output: layers/*.png, layers.json, diag_*.png
  -> engine2/rigby/layers2rigby.mjs   the layers become an unrigged Rigby2D work file, then Rigby2D AutoRig runs
  -> engine2/rigby/fixjoints.mjs      the joints move onto the drawing's joints ("Bone only": the art does not
                                      move); weight painting (hip -> thigh top, chest -> upper arm); IK bend side
                                      as drawn
  -> engine2/rigby/animations.py      keys written with `rigby call batch_edit`, so the file stays editable in
                                      the Rigby2D editor
  -> assets/character_rigs/<id>/<id>.rigby  +  export/<id>.json/.atlas/.png
  -> engine2/rigby/raster.py          Rigby2D Python runtime -> textured triangles -> OpenCV, 2x supersampled
  -> engine2/rigby/face.py            Rhubarb mouth shapes + blinks on the character's own face
  -> engine2/rigby/proof.py           poses, walk sheet, close-ups, 720p video, technical QA
```

Rebuilding a rig (once per character): `python3 engine2/rigby/build_rig.py hari <rigby2d source folder>`.

**Skeleton:**
- root
- hip, with a weighted mesh on each leg
- chest
- neck, head
- upperarm, forearm, hand (each side); the arm is ONE weighted mesh that bends at the elbow
- thigh, shin, foot (each side); the leg is one weighted mesh that bends at the knee
- IK targets for the hands (switched off; arms are keyed FK) and the feet (on; feet are planted)

**Animations:**
- `idle` (breathing)
- `talk` (far arm explains, beats)
- `listen` (weight back, head tilt, nods; a different pose)
- `indicate` (open-hand "that way")
- `open_palms`
- `walk`: 1.1 s cycle, stride 156 rig px, 60 % stance. The cycle is contact, down, passing, up, then the same on the opposite side, with heel strike, toe-off, arm swing with forearm drag and hip bob.
- `sit_down`, `sit_talk` (onto a seat that the scene must draw)

**Framing:** a full shot shows the character at 70-73 % of the frame height, and a medium shot at about 81 % (knees up). The camera follows the walk. The body moves at exactly the planted foot's speed, `2*STEP/(DUTY*T)`.

## 4. QA

Technical QA is separate from artistic approval. `qa_report.json` fails when:
- a limb (arm+hand, leg+foot) is not one connected piece;
- a single part falls into more pieces than in the drawing (an elbow or knee gap);
- a layer changes size beyond 72-135 % (missing or broken costume);
- a planted foot moves more than 1.5 px per frame;
- the character touches the frame edge in a full shot;
- the rest pose differs from the drawing in more than 0.5 % of pixels;
- the video fails `videoqa` (resolution, fps, codecs, audio length, black frames).

Passing these checks is **not** approval.

**Known limits** (also listed in the report):
- There is no index-finger hand drawing. "Pointing" is an open-hand indicating gesture, and a real point needs one new hand drawing.
- The mouth shapes and blinks are drawn by code.
- Seated thighs show small seams at the back of the hip.
- There is one view only (three-quarter, facing right).
- There are no expressions beyond neutral.

## 5. GitHub Actions

Run `mode = rig_test` and, optionally, `character = hari`. It runs before every daily job and then returns. It does not:
- reply to comments,
- post,
- publish,
- change history,
- change schedules,
- change the website,
- call Cloudflare.

It does upload `work/rig_test/**` and `assets/character_rigs/**` as artifacts, and it sends the summary, the two videos and three sheets to Telegram.

## 6. Rollback

Delete:
- `engine2/rigby/`, `engine2/rigprep.py` and `assets/character_rigs/`;
- `rig_test_run` and its `MODE` line in `main.py`;
- the `rig_test` text, `RIG_CHARACTER` and the `work/rig_test` / `assets/character_rigs` artifact lines in the workflow;
- `tests/test_engine2_rig.py`;
- `.claude/skills/hybrid-2d-animation/` and `CLAUDE.md`.

No production path reads any of them.

## 7. POSE_FIRST_CHARACTER_PIPELINE (the owner's revision of 22 Nov 2026)

The previous rig is kept for comparison and is not deleted. The arm-lift test (`engine2/rigby/armlift.py`) shows why the old way is not enough. On the near arm, the old flattened artwork breaks at the shoulder and armpit from 30 degrees on:
- a hole at 30 degrees;
- a broken outline from 45 degrees;
- a pinched shoulder at 90 and 120 degrees.

The far arm comes out of the body pinched from 60 degrees.

The new order is: reference → **complete high-resolution pose pictures** → validation → owner looks → separation → layers → rig → animation → QA → approval.

- `engine2/posefirst.py` with `mode = pose_art` (manual, Hari only for now). It sets `pose_set` to `core` by default:
  - `master` (rigging pose, arms about 40 degrees out);
  - `arm45`, `arm90` and `arm120`;
  - `both_up`;
  - `point_index` (index finger).

  Other sets are `arms` (5 more), `legs` (7), `hands` (8 hand drawings) and `all`.
- Every pose is its own complete picture: 1280 x 1920 for a figure and 1024 x 1024 for hands. 1920 px per side is the maximum this provider allows (Cloudflare documentation: width and height 256-1920), so 2048 x 3072 is not possible with it. A bigger picture can be supplied by hand.
- The reference is sent shrunk inside 511 x 511 (the documentation says input images must be smaller than 512 x 512).
- Provider-independent: a file in `assets/character_art/hari/inbox/<pose>.png` is used instead of generating that pose, with no API call.
- Estimate by the published price, assuming whole tiles: about 318 neurons per figure, 1,908 for `core` and about 6,600 for `all`. This must not be run after the morning story runs have used the day's free allocation.
- Resume and failure handling: passed pictures are never redrawn, and a 429 stops the run cleanly. At most 2 attempts per pose per run and 4 in total. Rejected pictures are kept in `pose_first/rejected/`.
- The automatic checks only reject obvious failures:
  - one whole figure, not cut off;
  - a figure of 1450 px or more;
  - the original's colours;
  - the eyes present;
  - for the master: arms away from the body and legs apart.
- The arm-lift test runs on the complete drawings (`armlift_complete_poses.png`: rest → 45 → 90 → 120 → both up, with zooms of the shoulder and armpit) and, for comparison, on the old rig.

**Rule for the hybrid engine:** an arm above 60 degrees, both arms up and an index-finger point use the complete drawings. The rig is used only inside the range its artwork supports.

**After the pictures exist**, the master is prepared for the rig the same way as before (`prep.json` read off the picture at zoom). Its limbs are clear, so the joints have their own pixels. The overlap at every joint comes from the complete pictures, not from patches.

### Step 1 only (the owner's instruction of 22 Nov 2026)

`mode = pose_art` makes **only the six pictures**:
- master A-pose;
- right arm at 45, 90 and 120 degrees;
- both arms raised;
- index-finger pointing.

It then builds a labelled contact sheet and an old-vs-new comparison sheet.

What the run does and does not do:
- Each provider file is kept byte for byte in `assets/character_art/hari/pose_first/originals/`.
- Any API error, including HTTP 429, stops the run and the exact error is reported.
- It never uses a mock picture, old artwork or another provider. It refuses to run in MOCK mode.
- It does no segmentation, builds no rig and runs no arm-lift test.

The next steps start only after the owner approves the six pictures. The report always separates four kinds of artwork:
- OLD artwork (the reference, used only as the identity input);
- NEWLY GENERATED artwork;
- MOCK/TEST artwork (none);
- APPROVED artwork (none until the owner says so).
