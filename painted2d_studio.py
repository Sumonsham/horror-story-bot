"""PAINTED 2D CARTOON STUDIO - Night/Morning Story-to-Asset Scout & Builder."""
import datetime as dt
import json
import os
import re

import characters


_PROP_PATTERNS = [
    (r"শাড়ি|শাড়ি|saree|sari", "hanging crimson-stained Bengali cotton saree", "hanging crimson-stained Bengali saree draped over an iron wall nail, painted 2D horror prop", "wall", "sway"),
    (r"হারিকেন|লণ্ঠন|lantern|hurricane", "old brass hurricane lantern", "antique rusty brass hurricane oil lantern with glowing warm amber flame, painted 2D horror prop", "floor", "flicker"),
    (r"প্রদীপ|মোমবাতি|candle|diya|lamp", "flickering earthen oil lamp", "small earthen clay oil lamp with flickering flame, painted 2D horror prop", "table", "flicker"),
    (r"ডায়েরি|ডায়েরি|খাতা|বই|diary|book|register|ledger", "old leather-bound handwritten diary", "worn dusty leather-bound old diary with yellowed pages, painted 2D horror prop", "table", "static"),
    (r"চিঠি|খাম|letter|envelope", "yellowed old envelope letter", "aged torn yellowed paper letter with red wax seal, painted 2D horror prop", "table", "static"),
    (r"তালা|চাবি|lock|padlock|key", "heavy rusted iron padlock", "heavy antique rusted iron padlock and key, painted 2D horror prop", "wall", "static"),
    (r"আয়না|আয়না|mirror", "cracked antique wooden wall mirror", "old ornate dark wooden-framed wall mirror with a diagonal crack in the glass, painted 2D horror prop", "wall", "static"),
    (r"ঘড়ি|ঘড়ি|clock|watch", "antique wooden pendulum wall clock", "old dark wooden pendulum wall clock stopped at midnight, painted 2D horror prop", "wall", "static"),
    (r"পুতুল|doll", "eerie vintage porcelain doll", "old cracked vintage Bengali cloth and porcelain doll in faded red dress, painted 2D horror prop", "floor", "static"),
    (r"বাক্স|ট্রাঙ্ক|সিন্দুক|trunk|chest|box", "old iron-bound wooden trunk", "heavy antique weathered wooden storage trunk with rusted iron bands, painted 2D horror prop", "floor", "static"),
    (r"ছবি|ফটো|photograph|portrait|album", "framed faded vintage portrait", "dusty antique wooden picture frame with faded sepia portrait, painted 2D horror prop", "wall", "static"),
    (r"নৌকা|boat", "old wooden country boat", "weathered dark wooden Bengali country rowboat, painted 2D horror prop", "floor", "sway"),
]


def _infer_anchor_and_motion(prop_text):
    low = str(prop_text or "").lower()
    for rx, pname, pdesc, anchor, motion in _PROP_PATTERNS:
        if re.search(rx, low):
            return pname, pdesc, anchor, motion
    clean = re.sub(r"[^a-zA-Z0-9 ,'-]", " ", str(prop_text or "")).strip()
    if len(clean) >= 3:
        anchor = "wall" if any(w in low for w in ("wall", "nail", "hang", "clock", "mirror", "window", "door")) else (
            "table" if any(w in low for w in ("table", "desk", "book", "diary", "letter", "cup", "lamp")) else "floor"
        )
        motion = "sway" if any(w in low for w in ("hang", "cloth", "saree", "curtain", "lantern", "swing")) else (
            "flicker" if any(w in low for w in ("lamp", "candle", "flame", "torch", "bulb")) else "static"
        )
        return clean[:48], f"{clean[:90]}, painted 2D horror story prop", anchor, motion
    return None


def scout_story_assets(story, lang="bn"):
    scenes = story.get("scenes") or []
    setting = str(story.get("setting") or "").strip()
    chars = [c for c in (story.get("characters") or []) if isinstance(c, dict) and c.get("name")]

    bg_list = []
    seen_bg = set()
    scene_props_plan = {}

    for i, sc in enumerate(scenes):
        place = str(sc.get("place") or setting or "dark Bengali village night").strip()
        mood = str(sc.get("mood") or "creepy").strip()
        bg_key = characters.slug(f"{place}-{setting}")[:60]
        if bg_key not in seen_bg:
            seen_bg.add(bg_key)
            bg_list.append({"scene": i, "place": place, "setting": setting, "mood": mood, "key": bg_key})

        pspec = sc.get("production_spec") if isinstance(sc.get("production_spec"), dict) else {}
        raw_props = list(pspec.get("props") or [])
        hay = " ".join(
            [place, str(sc.get("action") or "")]
            + [f"{ln.get('text', '')} {ln.get('en', '')}" for ln in (sc.get("lines") or [])]
        )
        for rx, pname, pdesc, anchor, motion in _PROP_PATTERNS:
            if re.search(rx, hay, re.I) and not any(pname.lower() in str(rp).lower() for rp in raw_props):
                raw_props.append(pname)

        picked = []
        used_pids = set()
        for rp in raw_props[:3]:
            inf = _infer_anchor_and_motion(rp)
            if not inf:
                continue
            pname, pdesc, anchor, motion = inf
            pid = characters.slug(pname)[:48]
            if pid in used_pids:
                continue
            used_pids.add(pid)
            picked.append({
                "id": pid,
                "name": pname,
                "desc": pdesc,
                "anchor": anchor,
                "motion": motion,
            })
        scene_props_plan[i] = picked

    return {
        "characters": chars,
        "backgrounds": bg_list,
        "scene_props": scene_props_plan,
    }


def build_story_assets(
    story,
    assets_dir,
    cache_dir,
    image_fn=None,
    upload_fn=None,
    slot_key="",
    series_names=(),
    seed=101,
    max_new_images=45,
    log=print,
):
    lib = characters.Library(
        assets_dir,
        cache_dir,
        image_fn=image_fn,
        upload_fn=upload_fn,
        log=log,
        style=characters.PAINTED_2D_STYLE,
    )
    scout = scout_story_assets(story)
    fixed = {str(x).lower() for x in (series_names or ())}
    day_key = str(slot_key or dt.date.today().isoformat()).split("@")[0]

    def _can_make():
        return lib.image_fn is not None and lib.stats["images_made"] + lib.stats["bg_made"] + lib.stats["props_made"] < max_new_images

    records, by_name = {}, {}
    for idx_c, c in enumerate(scout["characters"]):
        nm = str(c["name"]).strip()
        nm_low = nm.lower()
        cid = characters.char_id(c, series=nm_low in fixed, story_key=day_key)
        if not _can_make():
            lib.image_fn = None
        rec = lib.ensure(c, cid, need=characters.BASE_SET, seed=seed + idx_c * 37)
        records[cid] = rec
        by_name[nm_low] = rec
        if c.get("name_local"):
            by_name[str(c["name_local"]).strip().lower()] = rec

    bgs_per_scene = []
    scenes = story.get("scenes") or []
    setting = str(story.get("setting") or "").strip()
    for i, sc in enumerate(scenes):
        if not _can_make():
            lib.image_fn = None
        bg_pair = lib.background(
            sc.get("place", ""),
            setting,
            sc.get("mood", "creepy"),
            seed=seed + 500 + i,
        )
        bgs_per_scene.append(bg_pair)

    props_per_scene = {}
    for i, plist in scout["scene_props"].items():
        built_props = []
        for pi, pr in enumerate(plist):
            if not _can_make():
                lib.image_fn = None
            p_path, p_key = lib.prop(pr["name"], pr["desc"], seed=seed + 900 + i * 7 + pi)
            if p_path and os.path.exists(p_path):
                item = dict(pr, id=p_key, path=p_path)
                built_props.append(item)
        props_per_scene[i] = built_props

    lib.save()
    return records, by_name, bgs_per_scene, props_per_scene, dict(lib.stats)
