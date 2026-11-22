# Hybrid 2D MVP - implementation plan

Principle: reuse what exists (library, Rigby2D rig, arm-lift test, scene engine, videoqa). Add only the missing
decision, safety, identity and test layers. Keep everything behind test modes. `HYBRID_2D_MODE` stays OFF and is read nowhere.

## Done in this step (`engine2/mvp.py`, three test modes, one test file)

**1. Rig safety**
- `rig_limits`: the safe arm lift per side. It is the rest angle plus 10 deg, or the last step the arm-lift test passed.
- `anim_safety`: the largest lift in every rig animation.
- `clamp_arms`: eases the upper arm and forearm back together until the lift is inside the limit.

**2. Hybrid decision engine (`decide`)**

For each of the ten MVP actions, the engine picks one of these:

| Method | Used when |
|---|---|
| A, rig | the rig is safe for this action |
| A, rig in the safe range | the legs, head and mouth animate; the arms are eased back |
| B, complete drawing | a drawing exists for this action |
| C, static drawing | only a still picture is available |
| MISSING | nothing honest is available; this is reported |

The rules:
- Production mode counts only owner-approved assets.
- An owner rejection always wins.

**3. Identity check (`identity`)**
- Lab colour per region: hair, face, shirt, trousers, feet.
- Hue-histogram correlation of the whole figure.
- Face-structure correlation.
- Verdict: CONSISTENT, NEEDS_REVIEW or MISMATCH. It never approves anything.

**4. Complete poses (`ComplexPose`, `figure_rgba`)**
- The background is removed by a flood-fill from the border, together with the grey ground shadow.
- Each drawing is scaled to the rig's figure height and stood on the same ground line, so nothing jumps in size.

**5. Test modes**

| Mode | What it does |
|---|---|
| `engine_audit` | a JSON snapshot plus a Telegram summary |
| `asset_qa` | identity and cut-out checks, close-ups and a sheet |
| `render_test` | a 60-second 720p video, the decision table, a contact sheet and the video QA |

**6. Tests (`tests/test_engine2_mvp.py`)**
- The safety limits hold after clamping.
- Failed and rejected assets are never used.
- Production with nothing approved uses nothing.
- The identity check is not an approval.
- The cut-out keeps the inside of the figure and removes the shadow.
- Production stays isolated from the MVP.
- The workflow is wired correctly.

## Next steps (each needs the owner first)

1. **The owner looks** at the Hari sheets and decides in `APPROVALS.json`. This is Stage 3.
2. **New master artwork.** A master with the arms 35-45 deg away from the body. Either the owner supplies it (`assets/character_art/hari/inbox/master.png`) or one `pose_art` run is made for the master only, with the owner's permission (Cloudflare neurons).
3. **Re-rig.** `rigprep` on the approved master, then `layers2rigby`, `fixjoints`, the arm-lift test and the proof.
4. **Missing drawings.** sit, walk1-4, listen, scared, talk, and one hand sheet. They come from the owner or from approved pose_art runs, one set per run.
5. **Face marks for complete poses**, so they can talk and blink. Then expression drawings.
6. **Production integration** behind `HYBRID_2D_MODE`. Only after all the above are approved, and only with the owner's explicit go-ahead.
