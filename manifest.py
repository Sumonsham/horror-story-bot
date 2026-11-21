"""SCENE MANIFEST - the written plan of every scene, made from the story and the real voice timings.

scene = {
  "id", "index", "duration", "background": {"path", "id"}, "mood",
  "camera": {"move": push_in | pan_left | pan_right | track | handheld, "zoom": [from, to]},
  "effects": ["fog", "rain", "smoke", "lightning", "flicker", "shadow", "dust"],
  "characters": [{"id", "name", "mode": photo|silhouette, "x": 0..1, "scale", "ghost", "facing": -1|1}],
  "beats": [{"t0", "t1", "speaker": id|None (narrator), "expression": {id: expr}, "text", "subtitle": [t0, t1]}]
}
The same character keeps the same ID (so the same face and clothes) in every scene; voice and subtitle times
come from the audio that was really made, so the picture always follows the sound.
"""
import json

EMO_EXPR = {"scared": "fear", "fear": "fear", "terrified": "fear", "panic": "fear", "shout": "shock",
            "scream": "shock", "shock": "shock", "sad": "sad", "crying": "sad", "angry": "angry",
            "happy": "happy", "laugh": "happy", "whisper": "talking", "eerie": "talking", "normal": "talking"}
FX_WORDS = [("rain", ("rain", "storm", "monsoon", "বৃষ্টি", "drizzle")),
            ("smoke", ("smoke", "fire", "pyre", "burn", "ধোঁয়া", "আগুন", "chita", "শ্মশান", "crematorium")),
            ("lightning", ("thunder", "lightning", "storm", "বাজ", "মেঘ")),
            ("flicker", ("lamp", "lantern", "candle", "prodip", "প্রদীপ", "হারিকেন", "bulb", "torch", "power cut")),
            ("dust", ("abandoned", "old", "ruin", "dust", "পোড়ো", "পরিত্যক্ত", "attic")),
            ("shadow", ("shadow", "ছায়া", "figure", "someone", "footsteps", "corridor"))]


def effects_for(scene, mood):
    text = " ".join(str(x) for x in [scene.get("place", ""), scene.get("action", ""), " ".join(scene.get("ambience") or []),
                                     " ".join(scene.get("sounds") or []), scene.get("setting", "")]).lower()
    for ln in scene.get("lines") or []:
        text += " " + str(ln.get("text", "")).lower() + " " + " ".join(str(s.get("sound", "")) for s in (ln.get("sfx") or []))
    fx = ["fog"]
    for name, words in FX_WORDS:
        if any(w in text for w in words):
            fx.append(name)
    if mood in ("scare", "scary", "tense") and "shadow" not in fx:
        fx.append("shadow")
    return fx


def camera_for(index, mood, n_chars):
    if mood in ("scare", "scary"):
        return {"move": "handheld", "zoom": [1.08, 1.2]}
    if n_chars >= 2:
        return {"move": "track", "zoom": [1.1, 1.14]}
    return [{"move": "push_in", "zoom": [1.04, 1.16]}, {"move": "pan_right", "zoom": [1.14, 1.14]},
            {"move": "pan_left", "zoom": [1.14, 1.14]}][index % 3]


def build_scene(index, scene, beats, duration, chars, background, mood=None):
    """beats: [(t0, t1, speaker_name or None, emotion, text)] from the real audio.
    chars: {lower name: library record}. Returns the scene manifest (dict)."""
    mood = mood or scene.get("mood", "creepy")
    names = [str(n) for n in (scene.get("characters") or [])]
    for b in beats:                                    # whoever speaks is in the picture too
        if b[2] and b[2].lower() in chars and b[2] not in names:
            names.append(b[2])
    present = [chars[n.lower()] for n in names if n.lower() in chars][:3]
    slots = {1: [0.5], 2: [0.38, 0.62], 3: [0.32, 0.5, 0.68]}.get(len(present), [])
    people = []
    for k, rec in enumerate(present):
        ghost = str(rec["bible"].get("kind", "")).startswith("ghost")
        people.append({"id": rec["id"], "name": rec["bible"]["name"], "mode": rec.get("mode") or "silhouette",
                       "x": slots[k], "scale": 0.86 if ghost else 1.0, "ghost": ghost,
                       "facing": 1 if slots[k] < 0.5 else -1})
    by_name = {p["name"].lower(): p["id"] for p in people}
    out_beats = []
    for (t0, t1, spk, emo, text) in beats:
        sid = by_name.get(str(spk or "").lower())
        expr = {}
        for p in people:
            if p["id"] == sid:
                e = EMO_EXPR.get(str(emo or "").lower(), "talking")
                expr[p["id"]] = "talking" if e in ("talking",) else e
            else:
                expr[p["id"]] = "fear" if mood in ("scare", "scary") and not p["ghost"] else "neutral"
        out_beats.append({"t0": round(t0, 2), "t1": round(t1, 2), "speaker": sid, "expression": expr,
                          "text": str(text)[:200], "subtitle": [round(t0, 2), round(t1, 2)]})
    return {"id": f"scene_{index:02d}", "index": index, "duration": round(duration, 2), "mood": mood,
            "background": {"path": background[0], "id": background[1]},
            "camera": camera_for(index, mood, len(people)), "effects": effects_for(scene, mood),
            "characters": people, "beats": out_beats}


def save(manifests, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"scenes": manifests}, f, ensure_ascii=False, indent=1)
