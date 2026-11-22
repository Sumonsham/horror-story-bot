# Rollback guide (hybrid 2D MVP)

Nothing in production reads the MVP. To remove it completely:

1. Delete these files:
   - `engine2/mvp.py`
   - `tests/test_engine2_mvp.py`
   - `engine2/ENGINE_AUDIT.md`, `MVP_IMPLEMENTATION_PLAN.md`, `MVP_STAGE_STATUS.md`, `CHARACTER_ASSET_GUIDE.md`, `RIGGING_GUIDE.md`, `VISUAL_QA_REPORT.md`, `GITHUB_ACTIONS_GUIDE.md`, `ROLLBACK_GUIDE.md` and `DEPENDENCIES.md`
2. In `main.py`, delete:
   - the block from `# ==== engine 2 MVP` to the end of `render_test_run()`;
   - the three `MODE` lines `engine_audit`, `asset_qa` and `render_test` inside `main()`.
3. In `.github/workflows/horror-story.yml`, delete:
   - the three new `work/...` artifact lines;
   - the three `!= 'engine_audit' / 'asset_qa' / 'render_test'` conditions (in the "Remember this story" step and the `site` job);
   - the sentence about the three modes in the `mode` description.

Or simply revert the commit that added the MVP on GitHub. No data, history, schedule or production setting has to be restored, because none was changed.

**Verified:** with the three new modes unused, a `MOCK=1` run of the whole test suite passes. The production paths (`ANIM_MODE` empty, `ART_MODE` off) are byte-for-byte the same code as before, apart from the three dispatch lines, which only react to the new mode names.

**Hip cap (rig change):** copy `assets/character_rigs/hari/originals_before_hipcap/leg_r.png` and `leg_l.png` back to `layers/`, copy `hari.png` back to `export/`, and delete `hipcap.json`. The rig is then byte-for-byte as before.
