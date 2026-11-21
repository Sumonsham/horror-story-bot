"""STORY ENGINE - one scene of a real story -> the three assistants -> the cartoon animation engine (ANIM_MODE=cartoon).

Used by main.py only when the repository Variable ANIM_MODE is "cartoon"; any other value (or empty) keeps
the old picture video exactly as it was. If this fails for a scene, main.py makes that scene the classic way.
The scene's audio is the bot's own finished scene audio (narrator + every character's line): the lip-sync of
every character is cut from THAT audio at the exact time the voice step gave the line - so mouths move only
while that character speaks, and what the line says is what the assistants turned into animation.
Writes a per-scene match report (JSON) next to the clip; main.py gathers them into the Telegram team report.
"""
import json
import os
import re

import action_assistant
import animation_quality_check as qc
import animation_renderer
import cartoon_rig as rig
import location_assistant
import match_assistant
import scene_planner

LEDGERS = "engine_ledgers"


def _cid(name):
    s = re.sub(r"[^\w]+", "_", str(name).strip().lower(), flags=re.U).strip("_")
    return s or "x"


def cutout_art():
    """the 2.5D asset registry when ART_MODE=cutout (off by default - the code-drawn rig stays until it is proven)"""
    if os.environ.get("ART_MODE", "").strip().lower() != "cutout":
        return None
    import cutout_assets as CA
    return CA.Registry(os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "cartoon_parts"))


def cast_of(story_chars, designs=None):
    """the story's characters -> engine cast. designs: what the character designer saved at 2 AM with the story
    ({name: {"design"...}}); a character without a saved design is designed now from its look (same rules)"""
    import character_designer as CD
    out = []
    for k, c in enumerate(story_chars or []):
        if not isinstance(c, dict) or not c.get("name"):
            continue
        rec = (designs or {}).get(str(c["name"]))
        d = CD._typed(rec["design"]) if rec and rec.get("design") else CD.design(c)[0]
        aliases = [str(x) for x in (c.get("name_local"), c.get("en_name")) if x]
        out.append({"id": _cid(c["name"]), "name": str(c["name"]), "aliases": aliases, "design": d,
                    "ghost": bool(d.get("ghost"))})
    return out


def engine_clip(scene, beats, audio, out, story_chars, W=1280, H=720, fps=25, llm=None, log=print, idx=0, designs=None):
    """scene: the story scene (place, lines...); beats: [(t0, t1, speaker or None, emotion, text)] exactly as the
    voice step timed them; audio: this scene's finished audio. Returns the match result dict."""
    cast = cast_of(story_chars, designs)
    by_name = {}
    for c in cast:
        by_name[c["name"].lower()] = c["id"]
        for a in c["aliases"]:
            by_name[a.lower()] = c["id"]
        by_name[c["id"]] = c["id"]
    lines, last = [], None
    speakers = [by_name.get(str(b[2] or "").lower()) for b in beats]
    for k, (t0, t1, spk, emo, text) in enumerate(beats):
        sid = speakers[k]
        lis = None
        if sid:                                            # the listener: the next / previous other speaker
            for j in list(range(k + 1, len(beats))) + list(range(k - 1, -1, -1)):
                if speakers[j] and speakers[j] != sid:
                    lis = speakers[j]
                    break
        lines.append({"i": k + 1, "speaker": sid or "narrator", "listener": lis, "text": str(text), "feel": str(emo or ""),
                      "t0": round(float(t0), 2), "t1": round(float(t1), 2), "clip": "scene", "clip_t0": round(float(t0), 2)})
    scast = cast                                           # the planner puts on screen only who speaks / listens /
                                                           # does something the story says (a ghost that appears too)
    place = str(scene.get("place", ""))
    import subprocess
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", audio],
                               capture_output=True, text=True).stdout.strip() or 0) or (lines[-1]["t1"] + 1.0 if lines else 5.0)
    loc = location_assistant.analyse({"place": place, "lines": lines}, llm=llm, log=log)
    acts = action_assistant.analyse(lines, scast, place, llm=llm, log=log)
    for ln, an in zip(lines, acts["lines"]):
        ln["emotion"] = an["emotion"]
    match = match_assistant.judge(acts["lines"], loc["location"], [c["id"] for c in scast])
    art = cutout_art()                                     # 2.5D (ART_MODE=cutout): the AI-drawn parts when READY
    if art:
        import cutout_assets as CA
        for c in scast:
            rec = (designs or {}).get(c["name"]) or {"name": c["name"], "look": ""}
            key = CA.char_key({"name": c["name"], "look": rec.get("look", "")})
            if art.ready(key):
                c["design"] = dict(c["design"], cutout=(art.root, key))
    plan, reactions = scene_planner.plan_from_story({
        "id": f"scene{idx}", "location": loc["location"], "weather": loc["weather"], "duration": dur,
        "lead_in": min(2.0, lines[0]["t0"]) if lines else 2.0,
        "characters": [{"id": c["id"], "design": c["design"], "name": c["name"]} for c in scast],
        "lines": lines, "ops": match["ops"]})
    match_assistant.add_reactions(match, reactions)
    if art:                                                # the illustrated background of this place, when ready
        pr = art.index["plates"].get(loc["location"] + ("_rain" if (loc.get("weather") or {}).get("rain") else ""), {}) \
            or art.index["plates"].get(loc["location"], {})
        if pr.get("status") == "ready" and not plan.get("door"):          # (a door scene keeps the drawn room)
            plan["environment"].update(plate=os.path.join(art.root, pr["file"]), sky_parallax=0.75, dust=40 if loc["location"] == "house_interior" else 0, trees=[],
                                       bank_grass=0, clouds=2)
    import asset_qa                                        # BEFORE rendering: nobody the scene needs is missing
    needed = {l["speaker"] for l in lines if l["speaker"] != "narrator"} | {l["listener"] for l in lines if l.get("listener")} | \
        {o["who"] for o in match["ops"] if o.get("who")}
    sq = asset_qa.scene(plan, {c["id"] for c in scast}, needed, {})
    if not sq["pass"]:
        log(f"  scene {idx} check: " + "; ".join(sq["problems"]))
    clips = {"scene": (audio, dur)}
    work = os.path.join(os.path.dirname(os.path.abspath(out)), f"engine_chunks_{idx:02d}")
    rep, sc = animation_renderer.render(plan, clips, out, work, W, H, fps, audio, log=log)
    try:
        quality = qc.check(out, plan, rep, sc)
    except Exception as e:
        quality = {"error": str(e)[:120]}
    res = {"scene": idx, "place": place, "location": loc, "action_source": acts["source"], "lines": lines,
           "match": match, "quality": quality, "render": rep, "scene_check": sq,
           "drawn_by": getattr(sc, "asset_status", {}), "plate": plan["environment"].get("plate")}
    with open(os.path.splitext(out)[0] + "_match.json", "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1, default=str)
    led = os.path.join(os.path.dirname(os.path.abspath(out)), LEDGERS)
    try:
        action_assistant.collect(os.path.join(led, "animation_requests.json"), acts["lines"])
        match_assistant.collect(os.path.join(led, "missing_animations.json"), match)
    except Exception:
        pass
    log(f"  cartoon scene {idx}: {loc['location']} ({loc['status']}), match {match['counts']}")
    return res


def summary(work_dir):
    """all scenes' match reports -> (Bengali team-report rows, the full Bengali report text)"""
    scenes = []
    for f in sorted(os.listdir(work_dir)):
        if f.endswith("_match.json"):
            try:
                r = json.load(open(os.path.join(work_dir, f), encoding="utf-8"))
            except Exception:
                continue
            scenes.append({"id": r["scene"], "location": r["location"]["location"], "location_result": r["location"],
                           "location_source": r["location"].get("source"), "action_source": r["action_source"],
                           "lines": r["lines"], "match": r["match"]})
    if not scenes:
        return [], ""
    md, tot = match_assistant.report_bn(scenes)
    locs = {}
    for s in scenes:
        locs[s["location"]] = locs.get(s["location"], 0) + 1
    subs = sum(1 for s in scenes if s["location_result"].get("status") == "SUBSTITUTE")
    missing = sorted({it["act"] for s in scenes for ln in s["match"]["lines"] for it in ln["items"] if it["status"] == "MISSING"})
    rows = [f"🗺️ জায়গা-সহকারী: {len(scenes)}টা দৃশ্য - " + ", ".join(f"{k}×{v}" for k, v in locs.items())
            + (f" ({subs}টা কাছাকাছি বিকল্প)" if subs else ""),
            f"🎬 কাজ-সহকারী: " + ", ".join(f"{match_assistant.STATUS_BN[k]} {v}" for k, v in sorted(tot.items())),
            f"⚖️ মিল-সহকারী: " + (f"নেই এমন অ্যানিমেশন (দেখানো হয়নি, ভান করা হয়নি): {', '.join(missing)}" if missing
                                 else "গল্পের প্রতিটা দেখানোর মতো কাজ ভিডিওতে আছে")]
    return rows, md
