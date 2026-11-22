---
name: hybrid-2d-animation
description: Rig, animate and check a Daily Horror Story character as professional 2D cut-out / complete-pose animation (engine 2). Use for any work on character artwork, layers, rigs, poses, walk/sit/gesture animation, lip-sync, character framing or the rig_test / hybrid_test modes.
---

# Hybrid 2D animation (engine 2) - working rules

Read `engine2/RIG_PIPELINE.md` first. Production never uses engine 2 until the OWNER approves a character visually.

## Safety, always
- Never change the production engine, `ART_MODE`, schedules, history or the website. Never publish.
- Never call Cloudflare unless the owner explicitly asks for an artwork generation run (char_sheet), one character per run, no retry loops.
- Never write an approval. Only the owner edits `assets/character_library/APPROVALS.json`.
- A code test never approves art. Report technical QA and wait for the owner's visual decision.
- Keep originals, rejected assets and older versions. Never put secrets in the repository.

## Artwork: POSE FIRST (the owner's rule)
- Design for animation BEFORE cutting: complete high-resolution pose pictures first (`engine2/posefirst.py`, `mode = pose_art`, one character, Hari first), then separation, then the rig.
- Each pose is its own complete picture of the whole character. Never crop poses out of one combined image.
- A limb touching the body in the master means the master is rejected; do not repair it with patches.
- Owner-supplied artwork (`assets/character_art/<id>/inbox/<pose>.png`) always wins over generation.
- Never assume upscaling recovers anatomy.
- Run the arm-lift test (`engine2/rigby/armlift.py`; complete-pose version in `posefirst.armlift_from_poses`) before showing any rig. It must fail broken artwork, and a check that passes everything is useless.

## Artwork separation
- Identity = the ORIGINAL reference in the character library. Never redraw a character from a prompt.
- Preferred inputs are layered PSD/SVG, separate transparent PNGs, or complete approved pose drawings.
- From one flat drawing, separate ALONG THE DRAWN INK LINES (`engine2/rigprep.py` + `prep.json`). Never use rectangles or guesses.
  - Finish a line that stops short with a `close` polyline, read at 3-4x zoom with a coordinate grid.
  - Hidden regions: only a short own-colour strip under the covering part (`extend`).
  - If a pose would reveal more than that strip, request a new complete drawing instead of inventing pixels.
  - A line between a back part and a front part belongs to the front part (`line_owner`). A turned-up hem belongs to the trouser, and the trouser outline never belongs to the foot.
- After every prep, check that `lost_pixels` is about 0. Look at `diag_layers.png` (every layer alone) and `diag_parts_joints.png` at 100 % or more.

## Rigging
Use Rigby2D (MIT/Apache):
1. `layers2rigby.mjs` builds the work file and runs AutoRig.
2. `fixjoints.mjs` puts the joints on the drawing ("Bone only"), paints weights and sets the IK bend side.

Rules:
- The full bone list is root, hip, chest, neck, head, upperarm/forearm/hand and thigh/shin/foot on both sides, plus IK targets.
- Arms and legs are ONE weighted mesh each, so the elbow and knee bend without gaps.
- The tops of the limbs are weighted to the body (hip -> thigh top, chest -> upper arm).
- Keep limb thickness and costume continuity. Saree pallu and lower saree need their own meshes; ghosts need a floating body and a hair chain; children keep their proportions.
- The rest pose must equal the drawing. This is checked: `rest_pose_equals_drawing`.

## Hands
- A gesture uses a drawn hand. Never stretch or mirror a hand when the gesture or anatomy would be wrong.
- Missing hand shapes (pointing finger, fist, wave, namaste, holding, fear) need new hand drawings. Use one hand sheet per character, approved by the owner, with left and right hands tested separately.

## Motion
- **Walk:** contact, down, passing, up, then the same on the other side. IK feet are planted, and the body speed equals the foot's ground speed (`2*STEP/(DUTY*T)`). Include heel strike, toe-off, hip bob, opposite arm swing and forearm drag. Check the planted-foot slide stays under 1.5 px per frame.
- **Sit:** only on a seat the scene draws. The hips go down and back onto it, the feet stay planted and the knees go forward.
- **Talk:** Rhubarb `-r phonetic` (language independent) gives the mouth shapes; add small head beats and hand beats. Listening is its own pose, never the talking pose.
- **Complex actions** (running, falling, fighting, dramatic reactions, saree swirls, ghost transformations) use COMPLETE pose drawings, not the rig.

## Framing
- Full shot: 55-75 % of the frame height. Medium shot: 65-85 % (knees up). Close-up: face plus upper torso.
- Hands and feet stay inside a full shot. Two characters must both keep readable space.

## Visual QA (`python3 engine2/rigby/proof.py <id>` or `mode = rig_test`)
- Produce: the original, clean artwork, layers, joints, open palms, indicate, talk, listen, sit on a stool, the walk sheet, hand and foot close-ups at 100 % and 300 %, the 720p video and the slow walk video.
- A pose fails on: a detached or missing hand or foot, an elbow or knee gap, foot sliding, cropping in a full shot, a wrong face, a broken costume, or missing artwork.
- Inspect frames yourself at 100 % before reporting, and say plainly what still looks wrong.
