# Daily Horror Story bot - notes for Claude

## Character animation (engine 2)
Use the project skill `.claude/skills/hybrid-2d-animation/SKILL.md` for ANY of the following:
- character artwork, layers, rigs or poses;
- walk, sit, gesture or lip-sync animation;
- character framing;
- the `char_sheet`, `library_sync`, `hybrid_test` or `rig_test` modes.

Ground rules (details in the skill and `engine2/RIG_PIPELINE.md`):
- Production stays on the existing engine. `ART_MODE` stays off, and engine 2 is never enabled without the owner's visual approval.
- Never publish, never change history, schedules or the website from a test mode, and never call Cloudflare without an explicit request.
- Only the owner writes approvals (`assets/character_library/APPROVALS.json`). Technical QA is not approval.
- No secrets, tokens or personal data in the repository.
