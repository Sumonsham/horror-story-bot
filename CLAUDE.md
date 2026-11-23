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

## The TV cartoon (tvtoon) is production (owner's decision, 23 Nov 2026)
- The owner decided that the horror story now comes out as a cartoon. `horror-story.yml` sets `ANIM_MODE=tvtoon` by default; the repo variable `TVTOON_OFF=1` turns it off.
- `tvtoon/bot.py` replaces only the scene pictures. The bot's own lines, voices, sound, subtitles, thumbnail and uploads are unchanged. A scene that fails is made the classic way.
- Voices: tests use Chirp only; the normal story mode uses Gemini.
- Approvals: the owner gave a standing approval for every tvtoon character (`tvtoon/approvals.json` `_all`). He is not to be asked again.
