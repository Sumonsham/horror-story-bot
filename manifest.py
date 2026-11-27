"""SCENE MANIFEST - the written plan of every scene, made from the story and the real voice timings."""
import json

EMO_EXPR = {
    "scared": "fear", "fear": "fear", "terrified": "fear", "panic": "fear",
    "shout": "shock", "scream": "shock", "shock": "shock",
    "sad": "sad", "crying": "sad", "angry": "angry",
    "happy": "happy", "laugh": "happy",
    "whisper": "talking", "eerie": "talking", "normal": "talking",
}
FX_WORDS = [
    ("rain", ("rain", "storm", "monsoon", "বৃষ্টি", "drizzle")),
    ("smoke", ("smoke", "fire", "pyre", "burn", "ধোঁয়া", "আগুন", "chita", "শ্মশান", "crematorium")),
    ("lightning", ("thunder", "lightning", "storm", "বাজ", "মেঘ")),
    ("flicker", ("lamp", "lantern", "candle", "prodip", "প্রদীপ", "হারিকেন", "bulb", "torch", "power cut")),
    ("dust", ("abandoned", "old", "ruin", "dust", "পোড়ো", "পরিত্যক্ত", "attic")),
    ("shadow", ("shadow", "ছায়া", "figure", "someone", "footsteps", "corridor")),
]


def effects_for(scene, mood):
    text = " ".join(str(x) for x in [
        scene.get("place", ""), scene.get("action", ""),
        " ".join(scene.get("ambience") or []),
        " ".join(scene.get("sounds") or []),
        scene.get("setting", ""),
    ]).lower()
    for ln in scene.get("lines") or []:
        text += " " + str(ln.get("text", "")).lower() + " " + " ".join(
            str(s.get("sound", "")) for s in (ln.get("sfx") or [])
        )
    fx = ["fog"]
    for name, words in FX_WORDS:
        if any(w in text for w in words):
            fx.append(name)
    if mood in ("scare", "scary", "tense") and "shadow" not in fx:
        fx.append("shadow")
    return fx


def camera_for(index, mood, n_chars):
    if mood in ("scare", "scary"):
        return {"move": "handheld", "zoom": [1.06, 1.18]}
    if n_chars >= 2:
        return {"move": "track", "zoom": [1.06, 1.13]}
    return [
        {"move": "push_in", "zoom": [1.04, 1.16]},
        {"move": "pan_right", "zoom": [1.10, 1.14]},
        {"move": "pan_left", "zoom": [1.10, 1.14]},
    ][index % 3]


def _beat_action(text, emo, is_speaker, is_first_beat, is_ghost):
    low = str(text or "").lower()
    if is_ghost:
        return "ghost_float"
    if any(w in low for w in ("walk", "enter", "step in", "come in", "হাঁট", "ঢুক", "এগিয়ে")):
        return "walk_in" if is_first_beat else "walk_across"
    if emo in ("scared", "fear", "shock", "shout") or any(w in low for w in ("recoil", "step back", "flinch", "পিছিয়ে", "চমকে")):
        return "step_back" if is_speaker else "tremble"
    if is_speaker:
        return "talk_nod"
    return "listen"


def _layout_props(raw_props):
    out = []
    wall_slots = [0.22, 0.78, 0.50]
    table_slots = [0.50, 0.25, 0.75]
    floor_slots = [0.18, 0.82, 0.50]
    wi = ti = fi = 0
    for pr in (raw_props or [])[:3]:
        if not isinstance(pr, dict) or not pr.get("path"):
            continue
        anchor = str(pr.get("anchor") or "floor").lower()
        if anchor in ("wall", "hanging"):
            x = wall_slots[wi % len(wall_slots)]
            y = 0.34 if anchor == "hanging" else 0.45
            scale = 0.24
            wi += 1
        elif anchor == "table":
            x = table_slots[ti % len(table_slots)]
            y = 0.72
            scale = 0.18
            ti += 1
        else:
            x = floor_slots[fi % len(floor_slots)]
            y = 0.90
            scale = 0.22
            fi += 1
        out.append({
            "id": pr.get("id", "prop"),
            "name": pr.get("name", "prop"),
            "path": pr["path"],
            "anchor": anchor,
            "motion": pr.get("motion", "static"),
            "x": x,
            "y": y,
            "scale": scale,
        })
    return out


def build_scene(index, scene, beats, duration, chars, background, mood=None, props=None):
    mood = mood or scene.get("mood", "creepy")
    names = []
    for b in beats:
        if b[2] and b[2].lower() in chars and b[2] not in names:
            names.append(b[2])
    for n in (scene.get("characters") or []):
        sn = str(n)
        if sn.lower() in chars and sn not in names:
            names.append(sn)

    present = [chars[n.lower()] for n in names if n.lower() in chars][:2]
    if len(names) >= 3:
        third = chars.get(names[2].lower())
        if third and str(third.get("bible", {}).get("kind", "")).startswith("ghost"):
            present.append(third)

    slots = {1: [0.50], 2: [0.34, 0.66], 3: [0.28, 0.54, 0.76]}.get(len(present), [])
    people = []
    for k, rec in enumerate(present):
        ghost = str(rec["bible"].get("kind", "")).startswith("ghost")
        people.append({
            "id": rec["id"],
            "name": rec["bible"]["name"],
            "mode": rec.get("mode") or "photo",
            "x": slots[k],
            "scale": 0.90 if ghost else 1.0,
            "ghost": ghost,
            "facing": 1 if slots[k] <= 0.50 else -1,
        })

    by_name = {p["name"].lower(): p["id"] for p in people}
    out_beats = []
    for bi, (t0, t1, spk, emo, text) in enumerate(beats):
        sid = by_name.get(str(spk or "").lower())
        lid = next((p["id"] for p in people if p["id"] != sid), None)
        expr = {}
        act = {}
        for p in people:
            pid = p["id"]
            is_spk = (pid == sid)
            if is_spk:
                e = EMO_EXPR.get(str(emo or "").lower(), "talking")
                expr[pid] = "talking" if e == "talking" else e
            else:
                expr[pid] = "fear" if mood in ("scare", "scary") and not p["ghost"] else "neutral"
            act[pid] = _beat_action(text, str(emo or "").lower(), is_spk, bi == 0, p["ghost"])

        out_beats.append({
            "t0": round(t0, 2),
            "t1": round(t1, 2),
            "speaker": sid,
            "listener": lid,
            "expression": expr,
            "action": act,
            "text": str(text)[:200],
            "subtitle": [round(t0, 2), round(t1, 2)],
        })

    return {
        "id": f"scene_{index:02d}",
        "index": index,
        "duration": round(duration, 2),
        "mood": mood,
        "background": {"path": background[0], "id": background[1]},
        "camera": camera_for(index, mood, len(people)),
        "effects": effects_for(scene, mood),
        "props": _layout_props(props),
        "characters": people,
        "beats": out_beats,
    }


def save(manifests, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"scenes": manifests}, f, ensure_ascii=False, indent=1)
