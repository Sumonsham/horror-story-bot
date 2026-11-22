# GitHub Actions guide (engine 2 test modes)

Go to **Actions -> Daily Horror Story -> Run workflow**. Set `mode` and, if needed, `character`. Run test modes when no story run is due, because they share the run queue.

| mode | What it does | Uses Cloudflare? | Publishes? |
|---|---|---|---|
| `engine_audit` | a snapshot of engine 2 as JSON plus a Telegram summary: assets, approvals, the decision per action | no | no |
| `asset_qa` | identity and cut-out checks of every pose drawing, a cut-out sheet and 200 %/400 % close-ups | no | no |
| `rig_test` | rig poses, walk sheet, close-ups, 720p proof video, QA (existing) | no | no |
| `hybrid_test` | hybrid preview videos (existing) | no | no |
| `render_test` | a 60-second 1280x720 24 fps Hari test through the scene engine. The video itself is CLEAN (no labels); `NOT_APPROVED` is in its file name. It also gives the decision table, contact sheet, scale, walk and shadow sheets, the missing-pose report and video QA | no | no |
| `full_test` | a whole story with the cartoon engine as a dry run (existing) | no | no |
| `pose_art` | six new Hari pictures (existing). **Only with the owner's explicit permission**, because it uses Cloudflare's daily allocation | yes | no |

What every run gives you:
- **Artifacts:** the `horror-video` artifact (3 days) holds `work/engine_audit/**`, `work/asset_qa/**` and `work/render_test/**`.
- **Telegram:** a Bengali summary, the video and the sheets.

The engine 2 test modes never run the "Remember this story" commit step and never deploy the website. They also do not touch history, schedules, `ART_MODE` or `ANIM_MODE`.

**Option:** set `RENDER_PREVIEW=1` (an environment variable) for a fast 640x360, 12 fps preview instead of 720p.
