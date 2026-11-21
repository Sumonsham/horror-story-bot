"""STORY TEST - the three assistants + the engine on REAL story lines (the words heard = the words analysed).

    python story_test.py            -> work/story_test/: story_test.mp4 (16:9 1280x720 24 fps), story_report.json,
                                       story_match_report.md (Bengali), story_plans.json, ledgers

Three short scenes, cut from the voice samples already in assets/voice_samples (the real Gemini recordings of
two stories), so every spoken word is in the line the assistants read:
  A  "রাতের রাস্তা" - Abhishek and Sayan on the road at night; Haripada swinging a lantern in the middle of the road
  B  "জঙ্গলের ভেতরের রাস্তা" - Abhishek terrified; Sayan has gone stiff and does not answer
  C  "তারানাথের কুটির, ঝোড়ো রাত" - Taranath tells Kishori; the narrator: a knock on the hut's door in a storm;
     Taranath, frightened, about Madhusundari's unblinking eyes
  D  "অমাবস্যার রাত" - the narrator: '...মধুসুন্দরী তাঁর কুটিরে আবির্ভূত হন' - the yogini appears in the hut
Every character is built by the CHARACTER DESIGNER from its written look.
Line timings inside each recording are found automatically from the pauses (the production bot gets the exact
time of every line from its own voice step). Nothing paid, nothing downloaded; Gemini is used only when a key is
there (GEMINI_API_KEY on GitHub) - here the offline rules run and the report says so.
"""
import ast
import json
import os
import subprocess
import sys
import time
import wave

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import action_assistant  # noqa: E402
import animation_quality_check as qc  # noqa: E402
import animation_renderer  # noqa: E402
import cartoon_rig as rig  # noqa: E402
import environment_animation  # noqa: E402
import lip_sync  # noqa: E402
import location_assistant  # noqa: E402
import match_assistant  # noqa: E402
import scene_planner  # noqa: E402

OUT = os.path.join(HERE, "work", "story_test")
VS = os.path.join(HERE, "assets", "voice_samples")
SR = 44100
GAP = 0.4
LEAD = 2.2

# looks: Taranath, Kishori and Madhusundari exactly as the bot's own series describes them (main.py); the road
# story's three people were written for this test in the same form. The CHARACTER DESIGNER builds them all.
CAST = [
    {"id": "abhishek", "name": "Abhishek", "name_local": "অভিষেক", "gender": "male", "age": "adult", "kind": "human",
     "look": "a Bengali man of about forty, short black hair, thick moustache, a blue full-sleeve shirt and grey trousers"},
    {"id": "sayan", "name": "Sayan", "name_local": "সায়ন", "gender": "male", "age": "young", "kind": "human",
     "look": "a thin nervous young Bengali man of about twenty-two, messy black hair, a red checked shirt and blue jeans"},
    {"id": "haripada", "name": "Haripada", "name_local": "হরিপদ", "gender": "male", "age": "old", "kind": "human",
     "look": "an old village shopkeeper of about seventy, short white hair, white stubble, a white vest and white dhoti, "
             "a brown shawl, always carrying a hurricane lantern"},
    {"id": "taranath", "name": "Taranath", "name_local": "তারানাথ", "gender": "male", "age": "old", "kind": "human"},
    {"id": "kishori", "name": "Kishori", "name_local": "কিশোরী", "gender": "male", "age": "young", "kind": "human"},
    {"id": "madhusundari", "name": "Madhusundari", "name_local": "মধুসুন্দরী", "gender": "female", "age": "young", "kind": "ghost"},
]


def _series_looks():
    """Taranath / Kishori / Madhusundari: the looks written in main.py (read as text - main.py is not imported)"""
    import re
    src = open(os.path.join(HERE, "main.py"), encoding="utf-8").read()
    out = {}
    for name in ("TARANATH", "MADHU_CAST"):
        m = re.search(rf"^{name} = (\[.*?\n\])", src, re.S | re.M)
        for c in (ast.literal_eval(m.group(1)) if m else []):
            out[c["name"]] = c.get("look", "")
    return out


# (file, piece index, speaker, listener)
SCENES = [
    {"id": "A", "place": "রাতের রাস্তা, হরিপদর দোকানের সামনে", "cast": ["abhishek", "sayan", "haripada"],
     "lines": [("s_1112_032409_14", 0, "abhishek", "sayan"), ("s_1112_032409_14", 7, "abhishek", "haripada"),
               ("s_1112_032409_14", 8, "abhishek", "haripada"), ("s_1112_032409_14", 9, "abhishek", "haripada")]},
    {"id": "B", "place": "জঙ্গলের ভেতরের শর্টকাট, রাত", "cast": ["abhishek", "sayan"],
     "lines": [("s_1112_032431_15", 0, "abhishek", "sayan"), ("s_1112_032431_15", 2, "abhishek", "sayan"),
               ("s_1112_032431_15", 3, "abhishek", "sayan"), ("s_1112_032431_15", 4, "abhishek", "sayan"),
               ("s_1112_032431_15", 8, "abhishek", "sayan"), ("s_1112_032431_15", 9, "abhishek", "sayan")]},
    {"id": "C", "place": "তারানাথের কুটির, ঝোড়ো রাত", "cast": ["taranath", "kishori"],
     "lines": [("s_1111_093554_4", 0, "taranath", "kishori"), ("s_1111_093344_0", 8, "narrator", None),
               ("s_1111_093554_4", 4, "taranath", "kishori"), ("s_1111_093554_4", 5, "taranath", "kishori"),
               ("s_1111_093554_4", 6, "taranath", "kishori")]},
    {"id": "D", "place": "তারানাথের কুটির, অমাবস্যার রাত", "cast": ["taranath", "madhusundari"], "present": ["taranath"],
     "lines": [("s_1111_093344_0", 5, "narrator", None)]},
]


# ------------------------------------------------------------------ where each piece is inside its recording
def _pauses(x, hop=160):
    e = np.array([np.sqrt((x[i:i + hop] ** 2).mean() + 1e-12) for i in range(0, len(x) - hop, hop)])
    thr = np.percentile(e, 95) * 0.06
    q, out, i = e < thr, [], 0
    while i < len(q):
        if q[i]:
            j = i
            while j < len(q) and q[j]:
                j += 1
            if j - i >= 18:
                out.append((i * 0.01, j * 0.01))
            i = j
        else:
            i += 1
    return out


def piece_times(name):
    """the recording's pieces -> (start, end) by matching the pauses to the text lengths (dynamic programming)"""
    meta = json.load(open(os.path.join(VS, name + ".json"), encoding="utf-8"))
    P = meta["pieces"] if isinstance(meta["pieces"], list) else ast.literal_eval(meta["pieces"])
    x = lip_sync.load(os.path.join(VS, name + ".ogg"))
    T = len(x) / 16000
    ps = [(a, b) for a, b in _pauses(x) if a > 0.3]
    C, Lp = [(a + b) / 2 for a, b in ps] + [T], [b - a for a, b in ps] + [1.0]
    chars = [len(p["plain"].replace(" ", "")) for p in P]
    rate = sum(chars) / T
    N, M, INF = len(P), len(C), 1e18

    def cost(i, a, b, pl):
        e = chars[i] / rate
        return (b - a - e) ** 2 / (e + 0.5) - 1.2 * min(pl, 1.5)
    dp = [[INF] * M for _ in range(N)]
    bk = [[-1] * M for _ in range(N)]
    for j in range(M):
        dp[0][j] = cost(0, 0, C[j], Lp[j])
    for i in range(1, N):
        for j in range(M):
            for k in range(j):
                v = dp[i - 1][k] + cost(i, C[k], C[j], Lp[j])
                if v < dp[i][j]:
                    dp[i][j], bk[i][j] = v, k
    j, ends = M - 1, []
    for i in range(N - 1, -1, -1):
        ends.append(C[j])
        j = bk[i][j]
    ends = ends[::-1]
    starts = [0.0] + ends[:-1]
    trim = []
    for s, e in zip(starts, ends):                         # trim the silence at both ends
        for a, b in ps:
            if a <= s <= b:
                s = b - 0.08
            if a <= e <= b:
                e = a + 0.1
        trim.append((round(s, 2), round(e, 2)))
    return P, trim


def cut(name, a, b, out):
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(a), "-t", str(b - a), "-i", os.path.join(VS, name + ".ogg"),
                    "-ac", "1", "-ar", str(SR), "-af", f"afade=t=in:d=0.04,afade=t=out:st={max(0, b - a - 0.1):.2f}:d=0.1", out],
                   check=True)
    return out


def _pcm(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "s16le", "-ac", "1", "-ar", str(SR), "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.int16).astype("float32") / 32768.0


# ------------------------------------------------------------------ the sound of the place + the story's sounds
def ambience(plan, n):
    rng = np.random.default_rng(3)
    t = np.arange(n) / SR
    white = rng.standard_normal(n).astype("float32")
    brown = np.cumsum(white) / 400.0
    brown -= np.convolve(brown, np.ones(4001) / 4001, mode="same")
    wind = np.interp(t, t[::441], np.array([environment_animation.wind_at(x) for x in t[::441]]))
    loc = plan["location"]
    env = plan["environment"]
    out = brown * (0.03 if loc == "house_interior" else 0.10) * (0.4 + wind)
    if loc != "house_interior":
        for k in range(3):
            f0 = 4300 + 350 * k
            ch = (np.sin(2 * np.pi * f0 * t) * (np.sin(2 * np.pi * (18 + 3 * k) * t) > 0.6)
                  * (np.sin(2 * np.pi * (0.45 + 0.1 * k) * t + k) > 0.2))
            out += ch.astype("float32") * (0.006 if env.get("rain") else 0.012)
    rain = env.get("rain") or env.get("outside_rain") or 0.0
    if rain:
        hiss = np.convolve(white, [1, -0.9], mode="same") * 0.05 * rain
        out += hiss * (0.55 if loc == "house_interior" else 1.0)
    if loc == "cremation_ground":
        cr = (rng.uniform(0, 1, n) > 0.9993).astype("float32")
        out += np.convolve(cr, np.exp(-np.arange(300) / 40.0), mode="same") * 0.25 * rng.standard_normal(n)
    for s in plan["sfx"]:
        i0 = int(s["t"] * SR)

        def put(snd, j):
            if 0 <= j < n:
                out[j:j + len(snd)] += snd[: max(0, min(len(snd), n - j))]
        if s["type"] == "knock":
            for k in range(s.get("n", 3)):
                d = np.arange(int(0.12 * SR)) / SR
                put((np.sin(2 * np.pi * 95 * d) * 0.8 + rng.standard_normal(len(d)) * 0.25) * np.exp(-d * 45) * 0.9,
                    i0 + int(k * 0.42 * SR))
        elif s["type"] == "thunder":
            d = np.arange(int(2.5 * SR)) / SR
            put(np.convolve(rng.standard_normal(len(d)), np.ones(600) / 600, mode="same") * np.exp(-d * 1.6) * 3.0, i0)
        elif s["type"] == "creak":
            d = np.arange(int(1.0 * SR)) / SR
            put(np.sin(2 * np.pi * (300 + 120 * np.sin(d * 9)) * d) * np.exp(-d * 2) * 0.12, i0)
        elif s["type"] == "heartbeat":
            tt = s["t"]
            while tt < s["t1"]:
                for off, amp in ((0.0, 0.45), (0.22, 0.3)):
                    d = np.arange(int(0.18 * SR)) / SR
                    put(np.sin(2 * np.pi * 52 * d) * np.exp(-d * 22) * amp, int((tt + off) * SR))
                tt += 0.85
        elif s["type"] == "footsteps":
            tt = s["t"]
            while tt < s["t1"]:
                d = np.arange(int(0.12 * SR)) / SR
                put(np.convolve(rng.standard_normal(len(d)), np.ones(30) / 30, mode="same") * np.exp(-d * 30) * 0.5, int(tt * SR))
                tt += s.get("step", 0.47)
        elif s["type"] == "breath":
            tt = s["t"]
            while tt < s["t1"]:
                d = np.arange(int(1.1 * SR)) / SR
                env_ = np.sin(np.pi * d / 1.1) ** 2
                put(np.convolve(rng.standard_normal(len(d)), np.ones(12) / 12, mode="same") * env_ * 0.06, int(tt * SR))
                tt += 1.6
    return out


def scene_audio(plan, clips, path):
    n = int(plan["duration"] * SR)
    mix = ambience(plan, n)
    for c, (p, _) in clips.items():
        v = _pcm(p)
        i0 = int(plan["_clip_t0"][c] * SR)
        mix[i0:i0 + len(v)] += v[: max(0, min(len(v), n - i0))] * 1.15
    fi, fo = int(0.5 * SR), int(0.8 * SR)
    mix[:fi] *= np.linspace(0, 1, fi)
    mix[-fo:] *= np.linspace(1, 0, fo)
    mix = mix / (np.abs(mix).max() + 1e-6) * 0.9
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((mix * 32767).astype(np.int16).tobytes())
    return path


# ------------------------------------------------------------------ one scene: assistants -> plan -> video
def designed_cast(llm=None, log=print):
    """the CHARACTER DESIGNER builds every test character from its look (the library file stays in work/)"""
    import character_designer as CD
    looks = _series_looks()
    chars = [dict(c, look=c.get("look") or looks.get(c["name"], "")) for c in CAST]
    recs = CD.design_cast(chars, llm=llm, library=os.path.join(OUT, "cartoon_cast.json"), log=log)
    return [dict(c, aliases=[c["name_local"], c["name"]], design=CD._typed(recs[c["name"]]["design"]),
                 evidence=recs[c["name"]]["evidence"]) for c in chars]


def build_scene(sd, W, H, fps, llm=None, log=print, cast_all=None, art=None):
    cast = [c for c in (cast_all or designed_cast(llm, log)) if c["id"] in sd["cast"]]
    clips, lines, cur, cache = {}, [], LEAD, {}
    for k, (f, pi, spk, lis) in enumerate(sd["lines"]):
        if f not in cache:
            cache[f] = piece_times(f)
        P, times = cache[f]
        a, b = times[pi]
        name = f"{sd['id']}{k}"
        p = cut(f, a, b, os.path.join(OUT, name + ".wav"))
        clips[name] = (p, b - a)
        lines.append({"i": k + 1, "speaker": spk, "listener": lis, "text": P[pi]["plain"], "feel": P[pi].get("feel", ""),
                      "t0": round(cur, 2), "t1": round(cur + b - a, 2), "clip": name, "clip_t0": 0.0,
                      "source": f"{f} piece {pi} ({a:.2f}-{b:.2f}s)"})
        cur += b - a + GAP
    dur = cur + 1.4
    loc = location_assistant.analyse({"place": sd["place"], "lines": lines}, llm=llm, log=log)
    acts = action_assistant.analyse(lines, cast, sd["place"], llm=llm, log=log)
    for ln, an in zip(lines, acts["lines"]):
        ln["emotion"] = an["emotion"]
    match = match_assistant.judge(acts["lines"], loc["location"], [c["id"] for c in cast])
    plan, reactions = scene_planner.plan_from_story({
        "id": sd["id"], "location": loc["location"], "weather": loc["weather"], "duration": dur, "lead_in": LEAD,
        "characters": [{"id": c["id"], "design": c["design"], "name": c["name"]} for c in cast], "lines": lines,
        "ops": match["ops"], "present": sd.get("present", [])})
    match_assistant.add_reactions(match, reactions)
    if art is not None:                                    # 2.5D: AI-drawn parts + illustrated background when READY
        import cutout_assets as CA
        for c in plan["characters"]:
            cc_ = next(x for x in cast if x["id"] == c["id"])
            key = CA.char_key({"name": cc_["name"], "look": cc_.get("look", "")})
            if art.ready(key):
                c["design"] = dict(c["design"], cutout=(art.root, key))
        pr = art.index["plates"].get(loc["location"], {})
        if pr.get("status") == "ready" and not plan.get("door"):
            plan["environment"].update(plate=os.path.join(art.root, pr["file"]), sky_parallax=0.75, dust=40 if loc["location"] == "house_interior" else 0, trees=[], bank_grass=0, clouds=2)
    plan["_clip_t0"] = {l["clip"]: l["t0"] for l in lines}
    audio = scene_audio(plan, clips, os.path.join(OUT, f"scene_{sd['id']}.wav"))
    video = os.path.join(OUT, f"scene_{sd['id']}.mp4")
    log(f"scene {sd['id']}: {loc['location']} ({loc['status']}), {dur:.1f}s, {len(plan['camera'])} shots, "
        f"{len(plan['actions'])} actions, match {match['counts']}")
    rep, scene = animation_renderer.render(plan, clips, video, os.path.join(OUT, f"chunks_{sd['id']}"), W, H, fps, audio, log=log)
    quality = qc.check(video, plan, rep, scene)
    return {"id": sd["id"], "place_text": sd["place"], "location": loc["location"], "location_result": loc,
            "drawn_by": getattr(scene, "asset_status", {}), "plate": plan["environment"].get("plate"),
            "location_source": loc["source"], "action_source": acts["source"], "lines": lines, "actions": acts["lines"],
            "match": match, "plan": plan, "render": rep, "quality": quality, "video": video}


def run(W=1280, H=720, fps=24, llm=None, log=print):
    os.makedirs(OUT, exist_ok=True)
    t0 = time.time()
    cast_all = designed_cast(llm, log)
    scenes = [build_scene(sd, W, H, fps, llm, log, cast_all) for sd in SCENES]
    lst = os.path.join(OUT, "scenes.txt")
    with open(lst, "w") as f:
        f.writelines(f"file '{os.path.abspath(s['video'])}'\n" for s in scenes)
    final = os.path.join(OUT, "story_test.mp4")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy",
                    "-movflags", "+faststart", final], check=True)
    md, tot = match_assistant.report_bn(scenes)
    with open(os.path.join(OUT, "story_match_report.md"), "w", encoding="utf-8") as f:
        f.write(md)
    led = os.path.join(OUT, "ledgers")
    location_assistant.collect(os.path.join(led, "location_requests.json"), [s["location_result"] for s in scenes])
    for s in scenes:
        action_assistant.collect(os.path.join(led, "animation_requests.json"), s["actions"])
        match_assistant.collect(os.path.join(led, "missing_animations.json"), s["match"])
    dur = sum(s["plan"]["duration"] for s in scenes)
    rsec = sum(s["render"]["render_seconds"] for s in scenes)
    report = {"video": "story_test.mp4", "duration": round(dur, 1), "resolution": f"{W}x{H}", "fps": fps,
              "render_seconds": round(rsec, 1), "speed_x_realtime": round(rsec / dur, 2), "cpu_cores": os.cpu_count(),
              "match_totals": tot, "all_quality_pass": all(s["quality"]["all_pass"] for s in scenes),
              "characters": {c["name"]: c["evidence"] for c in cast_all},
              "scenes": [{"id": s["id"], "location": s["location"], "location_status": s["location_result"]["status"],
                          "location_reason": s["location_result"]["reason"], "action_source": s["action_source"],
                          "duration": s["plan"]["duration"], "match": s["match"]["counts"], "quality": s["quality"],
                          "lines": [{k: l[k] for k in ("i", "speaker", "text", "t0", "t1", "emotion", "source")} for l in s["lines"]]}
                         for s in scenes],
              "total_seconds": round(time.time() - t0, 1),
              "zero_cost": "কোনো paid API, paid GPU বা অনলাইন পরিষেবা ব্যবহার হয়নি (Python, NumPy, OpenCV, FFmpeg)"}
    with open(os.path.join(OUT, "story_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    with open(os.path.join(OUT, "story_plans.json"), "w", encoding="utf-8") as f:
        json.dump([s["plan"] for s in scenes], f, ensure_ascii=False, indent=1, default=str)
    log(md)
    log(json.dumps({k: v for k, v in report.items() if k != "scenes"}, ensure_ascii=False, indent=1))
    return report


if __name__ == "__main__":
    a = sys.argv[1:]
    run(int(a[0]) if a else 1280, int(a[1]) if len(a) > 1 else 720, int(a[2]) if len(a) > 2 else 24)
