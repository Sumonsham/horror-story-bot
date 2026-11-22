# Rigging guide (summary - the full pipeline is in `RIG_PIPELINE.md`)

1. **Approved master first** (arms away from the body). A master whose arms touch the body is rejected; it is never patched.
2. **Separation along the drawn ink lines:** run `engine2/rigprep.py` with a hand-checked `prep.json`. `lost_pixels` must be about 0. Check `diag_layers.png` and `diag_parts_joints.png` at 100 % or more.
3. **Build the rig:** `python3 engine2/rigby/build_rig.py <id> <rigby2d source>`. This runs `layers2rigby.mjs` (AutoRig) and then `fixjoints.mjs`, which moves the joints onto the drawing, paints the weights and sets the IK bend side.
4. **Arm-lift test** (`engine2/rigby/armlift.py`) at 0, 30, 45, 60, 90 and 120 deg on both arms. It records holes, the broken-outline share and the pinched-shoulder width.
   - The MVP turns this into a **safe limit** per arm (`mvp.rig_limits`).
   - Rig animations are measured against that limit (`mvp.anim_safety`).
   - An arm that goes past the limit is eased back (`mvp.clamp_arms`).
   - Movements beyond the limit need complete drawings.
5. **Proof:** `python3 engine2/rigby/proof.py <id>`, or `mode = rig_test`. It produces the poses, the walk sheet, close-ups, a 720p video and the QA report.

## Hari's state (23 Nov 2026)

**The rig is built from the original 576x1024 reference.** Its arms hang close to the body.

**Arm-lift results:**

| Arm | 30 deg | 45 deg | 60 deg and higher |
|---|---|---|---|
| Right | fails (21 px hole) | fails | fails (broken outline, pinched shoulder from 90 deg) |
| Left | fails | passes | fails |

**Safe limit (rest angle + 10 deg):** right 31.4 deg, left 31.0 deg.

**Animations that go past the limit:**

| Animation | Max lift |
|---|---|
| `talk` | 56 deg |
| `indicate` | 80 deg |
| `sit_talk` | 53 deg |
| `open_palms` | 43 deg |
| `walk` | 37 deg |

In tests these are eased back.

**Known rig defect:** a dark wedge at the front of the pelvis in the walk cycle. It is fixed only by a rebuild from a new, approved master.

## Fixes applied to Hari's rig (23 Nov 2026)

- **Waist sliver: fixed.** `engine2/rigby/hipcap.py` turns the hidden top of each trouser leg into a rounded own-colour cap, in the layer and the atlas. The originals are in `assets/character_rigs/hari/originals_before_hipcap/`. Waist exposure in the walk went from 175 px to 0. The rest pose is unchanged.
- **Feet: fixed at render time.** `mvp.fix_feet` keeps each foot's angle to the ground as keyed and pivots the roll on the toe or heel. The walk animation itself still keys the roll relative to the shin. A permanent fix is to re-key it in `animations.py` with the world angle, at the next rig rebuild, which needs the Rigby2D CLI.

To roll back the hip cap, copy the three files from `originals_before_hipcap/` back (`leg_r.png` and `leg_l.png` to `layers/`, `hari.png` to `export/`) and delete `hipcap.json`.
