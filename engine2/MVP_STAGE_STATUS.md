# MVP stage status - Hari (23 Nov 2026, after the visual remediation round)

Status labels: NOT_STARTED, IN_PROGRESS, BLOCKED, FAILED, PASSED_TECHNICAL, PENDING_HUMAN_VISUAL_APPROVAL, APPROVED.
Python tests never give APPROVED.

| Stage | Status | Evidence | Remaining | Rollback point |
|---|---|---|---|---|
| 0 Audit + backup | PASSED_TECHNICAL | `ENGINE_AUDIT.md`; baseline 94 tests passed before the change. The backup is the git history: everything is additive. | - | commit d8eef2c |
| 1 Reference + identity validation | PASSED_TECHNICAL | `mvp.identity` (region Lab, hue histogram, face structure) and `asset_qa` | the owner's eyes | - |
| 2 Master pose artwork | FAILED | The master's arms are too close to the body. arm120 is the wrong pose. | A new master from the owner's inbox drawing, or one approved `pose_art` run | - |
| 3 Artwork inspection + approval | PENDING_HUMAN_VISUAL_APPROVAL | `asset_qa` cut-out sheet and close-ups; `VISUAL_QA_REPORT.md` §1 | The owner decides in `APPROVALS.json` | - |
| 4 Layer separation (new master) | BLOCKED (by 2 and 3) | The existing rig layers are from the original reference (`lost_pixels` about 0) | rigprep on the approved master | - |
| 5 Skeletal rig | PASSED_TECHNICAL (existing rig) | `rig_test` proof; rest pose differs in 0.25 % of pixels | Rebuild after stage 4 | - |
| 6 Joint / deformation tests | FAILED for arm lifts of 30 deg and more; PASSED_TECHNICAL for legs and feet | arm-lift report; waist exposure 0 px in all 24 walk phases (was 175); no foot below its ground (test); hip-cap fix in `engine2/rigby/hipcap.py` | A rig from a new master must pass the arm-lift test; soft seam at the outer hip | `originals_before_hipcap/` |
| 7 Hybrid pose/action selection | PASSED_TECHNICAL | `mvp.decide` plus 9 tests; production mode uses nothing without approval | - | delete `engine2/mvp.py` |
| 8 Character animation + lip-sync | PASSED_TECHNICAL (with limits) | rig idle/talk/listen/walk/sit in the safe range; feet fixed; the lip-sync method is reported honestly (Rhubarb phonetic or amplitude) | Complete drawings have no mouth or blink; no expressions | - |
| 9 Background + scene animation | PASSED_TECHNICAL | two locations, atmosphere, cross-fade, per-foot contact shadows, the seat under the thighs | - | - |
| 10 720p rendering | PASSED_TECHNICAL | 60.0 s, 1280x720, 24 fps, H.264/yuv420p/AAC, gap 0 s, no black | - | - |
| 11 Full visual + technical QA | PENDING_HUMAN_VISUAL_APPROVAL | `VISUAL_QA_REPORT.md`, contact sheet, scale, walk and shadow sheets, missing-pose report, 111 tests passed | The owner looks at the video; the style difference between rig and drawings remains | - |
| 12 Production readiness | NOT READY | See the activation conditions below | - | `HYBRID_2D_MODE` stays OFF |

## Production activation conditions (all required)

1. Hari's master, the poses in use and the rig are owner-approved in `APPROVALS.json`.
2. The new master's rig passes the arm-lift test for every angle the animations use.
3. Drawings exist and are approved for sit, walk1-4, listen, scared, talk, and the hand sheet.
4. A `render_test` with only approved assets shows no MISSING action that the story needs.
5. The owner watches it and says yes. Only then is `HYBRID_2D_MODE` wired into `animation_renderer`, behind the flag, default OFF, and switched on by the owner.

## Missing / blocked actions (also in `missing_pose_report.json`)

| Action | Status | Why | Needed |
|---|---|---|---|
| both_arms_raised | BLOCKED | its drawing failed the automatic check and is not approved | the owner's approval of `both_up`, or a new drawing |
| scared | BLOCKED | no drawing, no expression | a scared full pose plus an afraid face, approved |

Production can use neither (`production_gate`), and the test video leaves both out.
