"""THE EPISODE LEDGER, THE QUALITY GATE AND THE DELIVERY PACKAGE (owner's master prompt, 24 Nov 2026:
Sections 3, 6, 15, 17, 18).

main.py makes the video exactly as before; this module adds, around it:

1. THE STORY LEDGER (Section 6). The final story is the single source of truth. Every scene ("paragraph") gets an
   ID (P01, P02 ...) and every sentence an ID (P01.S01 ...). Each sentence is followed through
       story -> the video's spoken lines (parts) -> its recorded audio -> the video's audio timeline.
   story_integrity_report.json says, per sentence: in the video once / taken out because it repeats what was said
   earlier (no_line_twice) / MISSING / said TWICE, and whether the order is kept and the ending is there.

2. THE QUALITY GATE (Section 15), before anything is posted. The finished MP4 is decoded from start to end:
       it must decode without errors, have a video and an audio stream, the right size and aspect, a length that
       matches its sound, and no stretch of black picture (>= 4 s) inside the story.
   A video that fails is NOT posted (Section 15/17): the bot says exactly why on Telegram, the MP4 stays as the
   run's artifact for 3 days. The story ledger is a report (a text match cannot prove a voice is wrong), it does
   not stop the post - but a missing ENDING is reported loudly.

3. THE DELIVERY PACKAGE (Section 18): work/episode_<date@slot>/ with complete_story.md, approved_screenplay.md,
   scene_breakdown.json, audio_timeline.json, dialogue_manifest.json, story_sources.json, seo_metadata.json,
   story_integrity_report.json, animation_qc_report.json, narration_consistency_report.json (voice_style.py),
   publication_report.json (the platform-confirmed IDs / links only), production_report.md and the thumbnail. The
   workflow keeps the folder as the run's artifact.

4. THE PRODUCTION TEAM REGISTER (Section 3): the 20 roles of the master prompt, each mapped to the part of the bot
   that really does that work (the bot's existing stages - nothing is duplicated), with what it took in, what it
   gave out and its status in THIS run, in production_report.md."""
import datetime as dt
import json
import os
import re
import subprocess

AGENTS = [  # (role, the bot's real stage, inputs -> outputs)
    ("Master Production Manager", "main.py run(): the order of all stages, retries, the 2-hour / slot rules",
     "the slot, history -> one finished, posted episode"),
    ("Horror Trend Researcher", "discovery.py (Google News / Trends, Wikipedia, YouTube trends) + trend rules",
     "the web -> today's idea / trend_used"),
    ("True Event Researcher", "true_web_story / honest_meta (sources, dates, places; 'based on true events' only "
     "with sources)", "the idea -> story_sources"),
    ("Horror Pattern Analyst", "style_teacher -> assets/style_model.json (hooks, escalation, climax, endings)",
     "the reference recordings -> the craft rules"),
    ("Original Story Writer", "choose_and_write / make_story (one-pass writer, STORY_STRENGTH rules)",
     "idea + craft -> the story"),
    ("Screenplay and Dialogue Writer", "the per-line plan (speaker, text, emotion, delivery, sfx, image, action)",
     "story -> scenes and lines"),
    ("Story Continuity Editor", "the chief editor pass, line_flow_check, ensure_ending, no_line_twice, textclean",
     "lines -> one seamless story, no line twice"),
    ("Voice Identity Director", "voice_style.py profile (assets/voice_style_profile.json, locked) + the approved "
     "Gemini narrator", "reference recordings -> narration direction"),
    ("Bengali Narration Engineer", "prepare_gemini_voices / make_scene_audio (Gemini, Chirp only as the approved "
     "fallback), voicecheck (repeats cut)", "lines -> clean line recordings"),
    ("Character and Casting Director", "tvtoon story.cast_story + the night library (prep.py)",
     "story characters -> actors"),
    ("Location and World Designer", "tvtoon story.place_of / rooms / outdoors / interiors",
     "scene places -> drawn worlds"),
    ("Character Asset and Rigging Director", "tvtoon prep.py Story Scout + Character Asset Builder (4 AM)",
     "the written story -> new characters in the library"),
    ("Character Acting and Lip-Sync Director", "tvtoon lipsync.py (Bengali visemes on the real audio) + animator "
     "(listening, reactions)", "line recordings -> mouths, faces"),
    ("Full Scene Animation Director", "tvtoon actions.py (every movement the script names) + animator / profile",
     "lines -> walks, runs, sits, gestures"),
    ("Environment Animation Director", "tvtoon worlds (parallax, clouds, trees, water, fog, rain, fire) + life.py",
     "places -> a moving world"),
    ("Sound Design Director", "make_scene_audio sfx / ambience / mood bed / freesound",
     "lines -> the scene's sound"),
    ("Cinematographer and Video Editor", "tvtoon scene.py camera (wide, medium, close, OTS, reaction, track) + "
     "build_video / render_clips", "scenes -> the edited episode"),
    ("SEO and Content Director", "titles, descriptions, tags, thumbnails (owner's own text), safety_check",
     "story -> seo_metadata"),
    ("Quality Control Director", "episode_ledger.quality_gate + story ledger + narration check",
     "the MP4 -> pass / do not post"),
    ("Publishing and Delivery Manager", "post_to_facebook / post_to_youtube (platform-confirmed IDs only) + "
     "this package", "the passed MP4 -> posts, links, files"),
]


def _key(s):
    return re.sub(r"[^\wঀ-৿ऀ-ॿ]", "", re.sub(r"<[^<>]{1,30}>", "", str(s or ""))).lower()


def _sentences(text):
    parts = [x.strip() for x in re.split(r"(?<=[।!?.])\s+(?=\S)", str(text or "").strip()) if x.strip()]
    out = []
    for x in parts:
        if out and (len(_key(x)) < 6 or len(_key(out[-1])) < 6):
            out[-1] += " " + x
        else:
            out.append(x)
    return out


# ----------------------------------------------------------------------------------------------- 1. the ledger
def build_ledger(story):
    led = []
    for pi, sc in enumerate(story.get("scenes") or []):
        for li, ln in enumerate(sc.get("lines") or []):
            for si, s in enumerate(_sentences(ln.get("text", ""))):
                if len(_key(s)) < 3:
                    continue
                led.append({"id": f"P{pi + 1:02d}.L{li + 1:02d}.S{si + 1:02d}", "paragraph": f"P{pi + 1:02d}",
                            "speaker": ln.get("speaker"), "text": s})
    return led


def integrity(story, segs, removed_keys=()):
    """the story's sentences against the video's audio timeline (segs = [(start, dur, narrator, text)]).
    Each story sentence takes the next unused place in the timeline where it is heard (so a sentence the story
    itself repeats on purpose is not 'twice'); a sentence heard MORE often than the story has it is 'said twice'."""
    from difflib import SequenceMatcher
    led = build_ledger(story)
    said = [(st, du, _key(tx)) for st, du, _n, tx in segs]
    used = set()

    def heard(k, kt):
        return bool(k) and (k in kt or (len(k) > 25 and SequenceMatcher(None, k, kt).ratio() > 0.85))
    rows, last_pos, order_ok = [], -1.0, True
    counts = {}
    for e in led:
        k = _key(e["text"])
        counts[k] = counts.get(k, 0) + 1
        hit = next(((n, st, du) for n, (st, du, kt) in enumerate(said) if heard(k, kt) and (n, k) not in used
                    and st + 0.01 >= last_pos), None) or \
            next(((n, st, du) for n, (st, du, kt) in enumerate(said) if heard(k, kt) and (n, k) not in used), None)
        if not hit:
            status = "removed: said earlier" if k in removed_keys or any(
                _key(o["text"]) == k for o in rows) else "MISSING"
            rows.append(dict(e, status=status))
            continue
        n, st0, du0 = hit
        used.add((n, k))
        if st0 + 0.01 < last_pos:
            order_ok = False
        last_pos = max(last_pos, st0)
        rows.append(dict(e, status="in the video", at=round(st0, 2), seconds=round(du0, 2)))
    twice = []
    for k, c in counts.items():
        n_heard = sum(1 for _st, _du, kt in said if heard(k, kt))
        if n_heard > c:
            twice += [r["id"] for r in rows if _key(r["text"]) == k][:1]
    for r in rows:
        if r["id"] in twice:
            r["status"] = "in the video, but HEARD MORE OFTEN than the story has it"
    missing = [r["id"] for r in rows if r["status"] == "MISSING"]
    tail = [r for r in rows if not r["status"].startswith("removed")][-1:]
    end_ok = bool(tail) and tail[0]["status"] != "MISSING"       # the story's last sentence is heard
    return {"sentences": len(rows), "in_video": sum(1 for r in rows if r["status"].startswith("in the video")),
            "missing": missing, "said_twice": twice, "order_kept": order_ok, "ending_present": end_ok,
            "ledger": rows}


# ----------------------------------------------------------------------------------------------- 2. the gate
def _probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height:format=duration",
                        "-of", "json", path], capture_output=True, text=True)
    try:
        return json.loads(r.stdout or "{}")
    except Exception:
        return {}


def quality_gate(video, audio_seconds=None, size=(1280, 720), log=print):
    """the finished MP4: decodes completely, has picture and sound, the right size, the right length, no black
    stretch. -> (passed, report)"""
    rep = {"file": os.path.basename(video), "checks": {}, "problems": []}
    if not os.path.exists(video) or os.path.getsize(video) < 100_000:
        rep["problems"].append("the video file is missing or empty")
        return False, rep
    pr = _probe(video)
    kinds = [s.get("codec_type") for s in pr.get("streams", [])]
    vs = next((s for s in pr.get("streams", []) if s.get("codec_type") == "video"), {})
    dur = float((pr.get("format") or {}).get("duration") or 0)
    rep["checks"].update(video_stream="video" in kinds, audio_stream="audio" in kinds, seconds=round(dur, 1),
                         size=[vs.get("width"), vs.get("height")])
    if "video" not in kinds:
        rep["problems"].append("no picture in the file")
    if "audio" not in kinds:
        rep["problems"].append("no sound in the file")
    if size and vs.get("width") and (abs(vs["width"] / max(1, vs["height"]) - size[0] / size[1]) > 0.02):
        rep["problems"].append(f"wrong picture shape {vs.get('width')}x{vs.get('height')}")
    if audio_seconds and dur and abs(dur - audio_seconds) > max(5.0, 0.03 * audio_seconds):
        rep["problems"].append(f"length {dur:.0f} s does not match its sound ({audio_seconds:.0f} s)")
    if dur < 20:
        rep["problems"].append(f"far too short ({dur:.0f} s)")
    # one full decode: decoding errors + black stretches
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", video, "-vf", "blackdetect=d=4:pix_th=0.04", "-an", "-f", "null",
                        "-"], capture_output=True, text=True)
    errs = [x for x in (r.stderr or "").splitlines() if re.search(r"(?i)error while decoding|corrupt|invalid data|"
                                                                    r"missing picture|concealing", x)]
    err = "\n".join(errs[:5]) if (errs or r.returncode != 0) else ""
    if r.returncode != 0 and not err:
        err = (r.stderr or "").strip().splitlines()[-1:][0] if (r.stderr or "").strip() else "ffmpeg failed"
    blacks = [(float(a), float(b)) for a, b in re.findall(r"black_start:([\d.]+)\s+black_end:([\d.]+)", r.stderr or "")]
    inner = [(a, b) for a, b in blacks if a > 3.0 and b < dur - 3.0]
    rep["checks"].update(decodes=not err.strip(), black_stretches=[[round(a, 1), round(b, 1)] for a, b in inner])
    if err.strip():
        rep["problems"].append("the video does not decode cleanly: " + err.strip()[:200])
    if inner:
        rep["problems"].append(f"{len(inner)} black stretch(es) inside the story (first at {inner[0][0]:.0f} s)")
    rep["passed"] = not rep["problems"]
    log("  quality gate: " + ("PASSED" if rep["passed"] else "FAILED - " + "; ".join(rep["problems"])))
    return rep["passed"], rep


# ----------------------------------------------------------------------------------------------- 3. the package
def write_package(work, key, story, parts, segs, title, description, tags, thumb, results, gate, integ, state,
                  log=print):
    d = os.path.join(work, "episode_" + re.sub(r"[^\w@-]", "_", str(key or dt.date.today().isoformat())))
    os.makedirs(d, exist_ok=True)
    J = lambda name, obj: json.dump(obj, open(os.path.join(d, name), "w", encoding="utf-8"), ensure_ascii=False,
                                    indent=1, default=str)
    with open(os.path.join(d, "complete_story.md"), "w", encoding="utf-8") as f:
        f.write(f"# {title}\n\n")
        for pi, sc in enumerate(story.get("scenes") or []):
            f.write(f"\n## P{pi + 1:02d} - {sc.get('place', '')}\n\n")
            f.write("\n".join(str(ln.get("text", "")) for ln in sc.get("lines") or []) + "\n")
    with open(os.path.join(d, "approved_screenplay.md"), "w", encoding="utf-8") as f:
        f.write(f"# {title}\n")
        for pi, sc in enumerate(story.get("scenes") or []):
            f.write(f"\n## SCENE P{pi + 1:02d} | {sc.get('place', '')} | {sc.get('mood', '')}\n\n")
            for li, ln in enumerate(sc.get("lines") or []):
                act = f"  _({ln['action']})_" if ln.get("action") else ""
                f.write(f"- **{ln.get('speaker', '')}** [{ln.get('emotion', '')}]: {ln.get('text', '')}{act}\n")
    J("scene_breakdown.json", [{"id": f"P{pi + 1:02d}", "place": sc.get("place"), "mood": sc.get("mood"),
                                "characters": sc.get("characters"), "ambience": sc.get("ambience"),
                                "lines": len(sc.get("lines") or [])} for pi, sc in enumerate(story.get("scenes") or [])])
    J("audio_timeline.json", [{"start": round(st, 2), "seconds": round(du, 2), "narrator": bool(n), "text": tx}
                              for st, du, n, tx in segs])
    J("dialogue_manifest.json", [{"part": i, "speaker": ln.get("speaker"), "emotion": ln.get("emotion"),
                                  "action": ln.get("action"), "text": ln.get("text")}
                                 for i, p in enumerate(parts) for ln in (p.get("lines") or [])])
    J("story_sources.json", {"true_label": story.get("true_label"), "sources": state.get("true_sources") or story.get("sources") or [],
                             "class": state.get("story_class"), "trend_used": state.get("trend_used")})
    J("seo_metadata.json", {"title": title, "description": description, "tags": tags})
    J("story_integrity_report.json", {k: v for k, v in (integ or {}).items()})
    J("animation_qc_report.json", state.get("tvtoon_qc") or {"note": "the classic pictures were used"})
    J("quality_gate_report.json", gate)
    pub = {"facebook_id": results.get("facebook"), "youtube_id": results.get("youtube"),
           "facebook_url": f"https://www.facebook.com/watch/?v={results['facebook']}" if results.get("facebook") else None,
           "youtube_url": f"https://youtu.be/{results['youtube']}" if results.get("youtube") else None,
           "errors": {k: v for k, v in results.items() if k.endswith("_error")},
           "posted": bool(results.get("facebook") or results.get("youtube"))}
    J("publication_report.json", pub)
    nc = os.path.join(work, "narration_consistency_report.json")
    if os.path.exists(nc):
        os.replace(nc, os.path.join(d, "narration_consistency_report.json"))
    if thumb and os.path.exists(thumb):
        try:
            import shutil
            shutil.copy(thumb, os.path.join(d, "thumbnail" + os.path.splitext(thumb)[1]))
        except Exception:
            pass
    with open(os.path.join(d, "production_report.md"), "w", encoding="utf-8") as f:
        f.write(f"# Production report - {title}\n\n")
        f.write(f"- quality gate: {'PASSED' if gate.get('passed') else 'FAILED: ' + '; '.join(gate.get('problems', []))}\n")
        if integ:
            f.write(f"- story ledger: {integ['in_video']}/{integ['sentences']} sentences in the video, "
                    f"{len(integ['missing'])} missing, {len(integ['said_twice'])} said twice, order "
                    f"{'kept' if integ['order_kept'] else 'CHANGED'}, ending {'present' if integ['ending_present'] else 'MISSING'}\n")
        vs = state.get("voice_style_check")
        if vs:
            f.write(f"- narration vs the reference style: {vs['matches']}/{vs['of']} match"
                    + (f" (differs: {', '.join(vs['differs'])})" if vs.get("differs") else "") + "\n")
        f.write(f"- Facebook: {pub['facebook_url'] or 'not posted'}\n- YouTube: {pub['youtube_url'] or 'not posted'}\n")
        f.write("\n## The production team (the bot's real stages)\n\n| # | Role | Done by | In -> out |\n|---|---|---|---|\n")
        for i, (role, how, io) in enumerate(AGENTS, 1):
            f.write(f"| {i} | {role} | {how} | {io} |\n")
        f.write("\n## Limits (said plainly)\n\n- The narrator keeps the approved Gemini voice: the reference "
                "presenter's own voice is not cloned (a real person's voice); his storytelling STYLE is measured and "
                "followed (voice_style.py).\n- Hand props (a lantern, a stick) are not drawn yet.\n")
    log(f"  episode package: {os.path.relpath(d, work)}/ ({len(os.listdir(d))} files)")
    return d
