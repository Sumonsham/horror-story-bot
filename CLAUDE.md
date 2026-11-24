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
- The Cartoon Studio (`tvtoon/studio.py`) turns the owner's own story into a finished episode. When he gives a story in chat, run `python -m tvtoon.studio <story.txt> <out> --voice ...` and deliver `final_episode.mp4` with its reports; don't ask about agents, backgrounds or characters. On GitHub, a story uploaded to `studio/inbox/` starts the "Cartoon Studio" workflow.
- The story moves the characters (`tvtoon/actions.py`): every movement the script names is acted; talking people face each other; places have their own people by day (`tvtoon/life.py`); the cinematic look is the default (`TVTOON_LOOK=flat` turns it off).
- Night character assets (owner's schedule, 23 Nov 2026): horror 2:00 write, 4:00 mode `assets` (only the new characters: `tvtoon/prep.py` Story Scout -> Character Asset Builder, saved in `assets/tvtoon_library.json`), 9:30 run for the 2 PM video, 15:00 run for the 8 PM video. The cartoon bot: 23:00 `write` (tomorrow's 3 stories), 2:00 `assets`, 2:30 / 8:30 / 14:30 runs for 7 AM / 1 PM / 7 PM. The animation is drawn to the voices' timing, so it is made in the video run after the voices.
- Every recorded line is checked for a voice that repeats itself (`tvtoon/voicecheck.py`); the repeat is cut.
- The cartoon sister bot (Sumonsham/hindi-story-bot) uses the same engine (`tvtoon/kids.py`, `tvtoon/kidsbot.py`); keep the `tvtoon/` folder identical in both repos.
- Narration style (owner, 24 Nov 2026): `voice_style.py` measured the approved reference recordings (assets/style_sample_*.mp3) into the LOCKED `assets/voice_style_profile.json` (speed, pauses, pitch movement, sentence endings, dynamics, whispers, opening / middle / final). The narrator's Gemini direction, the pauses between lines and a gentle narrator speed change (x0.90-1.06, pitch kept) follow it; every episode gets `narration_consistency_report.json`. The presenter's own voice is NOT cloned (a real person's voice) - only his style. Rebuild only when the owner changes the reference: `python voice_style.py build`.
- Before posting (`episode_ledger.py`): the story ledger (every sentence P01.L01.S01 followed into the audio timeline), the QUALITY GATE (full decode, picture + sound, size, length vs sound, no black stretch >= 4 s - a failed video is NOT posted, `QC_GATE=0` turns the gate off) and the delivery package `work/episode_<slot>/` (story, screenplay, timelines, manifests, SEO, reports, platform-confirmed links, the 20-role production register).
- Acting audit (owner, 24 Nov 2026): nobody stands still under the narration - `scene.py _idle_acting` gives every character its own small acts (looks round, glances, folds arms, hand to chin, nods, a step and back, a frightened flinch) wherever the story gives it nothing for ~3 s (`TVTOON_IDLE_ACT=0` turns it off); a long narration line is cut wide -> medium -> two-shot; the writer's words step back / grab / cover the nose / hold the lantern / look around are acted; an outdoor place the lists do not know is never drawn as a room; fog drifts, storms flash. The heartbeat "fear meter" overlay is OFF (repo variable `FEAR_METER=1` brings it back).
