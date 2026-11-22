# Visual QA report - Hari, remediation round (23 Nov 2026)

I looked at every sheet and frame named here myself, in the sandbox, at 100 % to 300 %. The **owner's visual approval is still required**. Nothing here approves anything.

## What changed since the first render test, and what I saw

| # | Issue | Source found | Fix | Evidence |
|---|---|---|---|---|
| 1 | Talking looked bigger than neutral | the talking scene used a medium shot (zoom 2.35); complete drawings were scaled by their bounding box (a raised hand made the body smaller) | one full-shot framing for every action; drawings scaled by their body height (head top to soles, raised hands excluded) and stood on the ground by their feet's centre | `character_scale_comparison.jpg`; in the video: body height 72.2-72.8 % for neutral, talking, listening, pointing and one arm raised (max 1.0 % from neutral) |
| 2 | Dark sliver at the waist in the walk | each trouser leg's HIDDEN top (under the pelvis) was a square, trouser-wide cut that included the pocket fold, a detached strip; when the leg swung it showed | `engine2/rigby/hipcap.py`: the hidden top becomes a rounded cap of the leg's own colour; the pocket line stays on the pelvis; the same pixels are changed in the layer and the atlas; originals are kept in `originals_before_hipcap/` | `walking_waist_closeups.jpg` (before / after at 240 %); exposed hidden pixels: up to 175 px per phase before, 0 in all 24 phases after; the rest pose is unchanged (383 px, as before) |
| 3 | Floating / sinking feet; no shadow | the walk keys each foot's heel-toe roll relative to the SHIN, so the foot's angle to the ground turned with the leg and the far foot's toe sank up to 44 rig px; no contact shadow at all | `mvp.fix_feet`: each foot keeps its angle to the ground plus the keyed roll; a roll that would push it below its own ground lifts the ankle (toe / heel pivot). `mvp.contact_shadow`: a small soft shadow per foot, at its own sole, fading when lifted, its strength following the floor's brightness | `ground_shadow_comparison.jpg`; no foot below its ground in any phase (test); soles within 2 px of the ground in every standing scene |
| 4 | The stool was under the feet, the hips in the air | the seat height was measured on the shins | `mvp.seat_from_pose`: the seat top goes exactly under the thighs (measured between hip and knee on the sitting pose), centred between hip and knee | frame at 49 s |
| 5 | Neutral shown for both_arms_raised and scared | a MISSING action was rendered as neutral | MISSING actions are taken OUT of the video (their time goes to the other scenes); `missing_pose_report.json`; `production_gate` blocks them; red MISSING / BLOCKED tiles on the contact sheet | contact sheet; report |
| 6 | Shirt colour of the pointing drawing | the generated drawing's colours differ from the reference (shirt dE 8.1, hair 9.5, face 10.5) | `mvp.harmonize`: each region's colour group is shifted to the reference colour; shapes, ink and shading stay; the original files are untouched | pointing shirt dE 8.1 -> 1.0, hair 9.5 -> 0, face 10.5 -> 0; arm90 shirt 3.6 -> 0 |
| 7 | Debug text in the video | labels and the watermark band were drawn into every frame | the video is clean (no label, no band); NOT APPROVED is in the file name, the report and the contact sheet | test `test_render_frames_carry_no_debug_overlay` |
| 8 | Lip-sync claims | - | the report says plainly what the mouth movement is (Rhubarb phonetic or amplitude), plus the Rhubarb path and version when it is present | `render_test_report.json` -> `checks.lip_sync` |

## What still looks wrong (seen in the frames)

- **The drawings and the rig are not the same drawing.** In pointing and one arm raised, the head is slightly larger relative to the legs, and the face is drawn a little differently (eyes, moustache shape). Colours now match. The proportions do not, and they cannot be matched without distorting the art. A real fix is drawings made from ONE approved master.
- **A small soft seam at the outer hip in the walk.** This is where the pelvis' fading edge meets the leg. It was there before, hidden under the sliver.
- **A toe-off dip of up to about 3 screen px** on the far foot at the very end of its stance.
- **Complete drawings have no mouth and no blink**, and no face expressions exist.
- **both_arms_raised and scared are not shown at all.** There are no approved drawings.
- **Lip-sync in this sandbox run was AMPLITUDE**, because Rhubarb could not be downloaded here. On GitHub the mode downloads Rhubarb, which is language-independent phonetic, not a Bengali phoneme model.

## Is the new video better than the previous one?

Yes, in the six ways that can be measured:
- one scale;
- no waist sliver;
- feet on the ground with real contact shadows;
- the stool under the thighs;
- matching colours;
- no debug text.

It is also more honest: it shows only the actions that exist.

It is still **not** ready for production. The style difference between the rig and the drawings remains, there is no approved master, and drawings are missing.
