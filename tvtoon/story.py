"""STORY -> EPISODE (23 Nov 2026): turns one of the bot's own stories (assets/today_scripts.json, the 'story' with
'characters' and 'scenes' -> 'lines') into a tvtoon episode automatically:

  * every story character gets an actor from the horror cast by kind (ghost / human), gender and age - each actor
    is used once, the story's own name is shown in the subtitles;
  * every story scene gets a location from its 'place' text (station, cremation ground, bamboo grove, pond, road,
    Kolkata street, old house / palace, a room) and the time of day from its words (night, dusk, day);
  * lines become dialogue (with the right listener), the narrator becomes a voice-over, emotions are mapped to the
    acting the engine knows, ghosts float in at their first line, a door opens when a ghost first appears in a room;
  * trains arrive at stations, a tram crosses a Kolkata street, a cycle or toto passes on a village road.

Nothing here invents story content: only what the story says is shown. Manual edits of the result are possible
(it is a normal episode spec)."""
import json
import os
import re

from tvtoon import characters as CH

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PLACE_WORDS = [  # first match wins (inside a vehicle before the station / street words)
    ("train_inside", ["compartment", "inside the train", "inside train", "in the train", "on the train", "train journey",
                      "coach of", "ট্রেনের কামরা", "কামরা", "ট্রেনে"]),
    ("bus_inside", ["inside the bus", "in the bus", "on the bus", "bus journey", "night bus", "বাসে", "বাসের ভেতর"]),
    ("tram_inside", ["inside the tram", "in the tram", "on the tram", "tram ride", "ট্রামে"]),
    ("ride", ["auto", "toto", "rickshaw", "e-rickshaw", "টোটো", "অটো", "রিকশা"]),
    ("station", ["station", "platform", "railway", "train", "local train", "স্টেশন", "প্ল্যাটফর্ম"]),
    ("shmashan", ["cremation", "shmashan", "burning ghat", "pyre", "graveyard", "cemetery", "শ্মশান", "কবর"]),
    ("bansh_bon", ["bamboo", "forest", "jungle", "woods", "grove", "বাঁশ", "জঙ্গল"]),
    ("pukur_ghat", ["pond", "ghat", "lake", "river", "pukur", "পুকুর", "ঘাট", "নদী"]),
    ("city_street", ["kolkata street", "city street", "tram", "street", "lane", "market", "কলকাতা"]),
    ("village_road", ["road", "highway", "path", "field", "paddy", "bridge", "রাস্তা", "মাঠ"]),
    ("ghar", ["room", "bedroom", "chamber", "office", "studio", "flat", "apartment", "kitchen", "hall", "interior", "inside", "veranda",
              "doorway", "hearth", "corridor", "attic", "ঘর", "বারান্দা"]),
    ("zamindar_bari", ["palace", "mansion", "zamindar", "haveli", "bungalow", "rajbari", "fort", "ruin", "house",
                       "জমিদার", "রাজবাড়ি", "বাড়ি"]),
    ("village_courtyard", ["courtyard", "village", "উঠোন", "গ্রাম"]),
]
NIGHT = ["night", "midnight", "dark", "moon", "lantern", "রাত", "অন্ধকার"]
DUSK = ["evening", "dusk", "sunset", "twilight", "সন্ধ্যা"]

EMO = {"scared": "scared", "terrified": "scared", "scare": "scared", "choking": "scared", "panic": "scared",
       "angry": "angry", "shout": "angry", "furious": "angry", "crying": "crying", "tragic": "sad", "sad": "sad",
       "happy": "happy", "laugh": "laughing", "laughing": "laughing", "surprised": "surprised", "shocked": "surprised"}
GHOST_EMO = {"eerie": "angry", "creepy": "laughing", "malicious": "laughing", "chilling": "angry", "ominous": "angry"}

ACTORS = {  # (kind, gender, age) -> actors in order of preference
    ("ghost", "female"): ["petni", "shakchunni"],
    ("ghost", "male"): ["brahmadaitya", "mechho_bhoot"],
    ("human", "male", "old"): ["shibu_dadu", "ojha", "bhattacharya"],
    ("human", "male", "adult"): ["abhishek", "ramu_chowkidar", "bhattacharya", "ojha"],
    ("human", "male", "young"): ["sayan", "abhishek"],
    ("human", "male", "child"): ["sayan", "bappa"],
    ("human", "female", "old"): ["mokkhoda", "sarala_thakuma"],
    ("human", "female", "adult"): ["parul", "riya", "lumi_didi"],
    ("human", "female", "young"): ["riya", "parul"],
    ("human", "female", "child"): ["kishori", "mili"],
}


def _age(a):
    a = str(a or "adult").lower()
    if a.isdigit():
        n = int(a)
        return "child" if n < 13 else "young" if n < 25 else "adult" if n < 58 else "old"
    if any(w in a for w in ("child", "kid", "boy", "girl")):
        return "child"
    if any(w in a for w in ("old", "elder", "aged")):
        return "old"
    if any(w in a for w in ("young", "teen")):
        return "young"
    return "adult"


def cast_story(characters, reveal=None):
    """story character name -> (actor id, name shown). A MALE ghost that first comes as an ordinary man (the story
    has a 'ghost_reveal' for him) is played by a human actor of his age, whose ghost form is that same man as a
    ghost ('<actor>__ghost'): the dead person himself. Female ghosts keep the designed ghosts (petni, shakchunni),
    which have their own ordinary-woman disguise."""
    used, out = set(), {}
    reveal = reveal or {}
    for ch in characters:
        name = ch.get("name")
        if not name or name.lower() in ("narrator", "কথক"):
            continue
        kind = "ghost" if str(ch.get("kind", "human")).lower() in ("ghost", "spirit", "demon", "entity") else "human"
        g = "female" if str(ch.get("gender", "male")).lower().startswith("f") else "male"
        if kind == "ghost" and g == "male" and name in reveal:
            prefs = [a for a in ACTORS.get(("human", "male", _age(ch.get("age"))), []) if a not in used and a in CH.SPECS]
            if prefs:
                used.add(prefs[0])
                out[name] = (prefs[0] + "__ghost", ch.get("name_local") or name)
                continue
        prefs = ACTORS.get((kind, g)) if kind == "ghost" else ACTORS.get((kind, g, _age(ch.get("age"))))
        prefs = list(prefs or []) + (["petni", "shakchunni"] if g == "female" and kind == "ghost" else [])
        pool = [a for a in prefs if a not in used] or [a for a in CH.horror_cast() if a not in used and
                                                       (CH.get(a).get("ghost") is not None) == (kind == "ghost")]
        actor = pool[0] if pool else prefs[0]
        used.add(actor)
        out[name] = (actor, ch.get("name_local") or name)
    return out


def place_of(text):
    t = (text or "").lower()
    for loc, words in PLACE_WORDS:
        if loc == "ride":                                   # whole words only ('auto' is not 'autumn')
            if any(re.search(r"(?<![a-z])" + re.escape(w) + r"(?![a-z])", t) for w in words):
                return loc
        elif any(w in t for w in words):
            return loc
    return "ghar"


def hours_of(text, mood="", inherit=None):
    """the time of day: what the place text says wins; when it says nothing the scene keeps the time of the scene
    before it (a night story stays night), and only the very first scene falls back to the story's words / mood"""
    t = (text or "").lower()
    if any(w in t for w in ("daytime", "morning", "noon", "sunlight", "afternoon", "দুপুর", "সকাল")):
        return 13.0
    if any(w in t for w in DUSK) or "sunset" in t:
        return 18.2
    if any(w in t for w in NIGHT):
        return 21.5
    if inherit is not None:
        return inherit
    return 21.0 if str(mood).lower() in ("scare", "eerie", "creepy") else 15.5


def episode_from_story(story, max_scenes=None, max_lines=None, aspect="16:9"):
    ghosts_seen = set()
    # the bot's story says in which scene the LISTENERS first learn that a character is a ghost ("ghost_reveal":
    # {name: scene number, 1 = first}). Before that scene the ghost comes as an ordinary person (its disguise); in
    # that scene (or the first later one where it speaks) the disguise falls in front of everyone.
    reveal = {}
    for n_, v_ in (story.get("ghost_reveal") or {}).items():
        try:
            reveal[n_] = int(v_)
        except (TypeError, ValueError):
            pass
    revealed = set()
    cast = cast_story(story.get("characters", []), reveal)
    scenes = []
    whole = " ".join(str(story.get(k, "")) for k in ("title", "logline", "premise", "setting", "summary")).lower()
    hour = None
    if any(w in whole for w in NIGHT):                     # a night story: every scene is night unless it says otherwise
        hour = 21.5
    for si, sc in enumerate(story.get("scenes", [])[: max_scenes or 999]):
        place = sc.get("place", "")
        loc = place_of(place)
        ride_kind = None
        if loc == "ride":                                   # a scene IN an auto / toto / rickshaw: on the road
            ride_kind = "auto" if any(w in place.lower() for w in ("auto", "অটো")) else "toto"
            city = any(w in place.lower() for w in ("kolkata", "city", "street", "কলকাতা"))
            loc = "city_street" if city else "village_road"
        lines = [ln for ln in sc.get("lines", []) if (ln.get("text") or "").strip()][: max_lines or 999]
        speakers = []
        for ln in lines:
            sp = ln.get("speaker")
            if sp in cast and sp not in speakers:
                speakers.append(sp)
        speakers = speakers[:4] if not ride_kind else speakers[:3]
        inside = loc.endswith("_inside")
        offs = [-280, 280, -760, 760]
        cast_spec, ids = [], {}
        disguised = {sp for sp in speakers if sp in reveal and sp not in revealed and CH.get(cast[sp][0]).get("ghost") is not None}
        change_here = {sp for sp in disguised if si + 1 >= reveal[sp]}
        for k, sp in enumerate(speakers):
            actor, shown = cast[sp]
            ghost = CH.get(actor).get("ghost") is not None and sp not in disguised
            if inside:                                      # benches facing each other across the carriage
                cast_spec.append({"id": actor, "x": [1250, 1950, 700, 2500][k], "z": 0.0, "name_bn": shown})
            elif ride_kind:
                cast_spec.append({"id": actor, "x": 600, "z": 0.0, "name_bn": shown})
            else:
                cast_spec.append({"id": actor, "x": 1600 + offs[k], "z": 0.45 if ghost else 0.05 * k, "name_bn": shown})
            if sp in disguised:
                cast_spec[-1]["disguise"] = True
            ids[sp] = actor
        hour = hours_of(place, sc.get("mood", ""), inherit=hour)
        world = {"hours": [[0, hour]], "wind": 0.5}
        pl = place.lower()
        if any(w in pl for w in ("rain", "storm", "বৃষ্টি", "ঝড়")):
            world["rain"] = [[0.0, 9999.0]]
            world["wind"] = 0.9 if "storm" in pl or "ঝড়" in pl else 0.6
        if any(w in pl for w in ("mist", "fog", "কুয়াশা")):
            world["fog"] = 0.45
        beats = [{"pause": 1.4}]
        vehicles = []
        if inside:
            for k, sp in enumerate(speakers):
                beats.append({"who": ids[sp], "sit": True, "prop": False, "already": True, "side": True, "with_prev": True})
            if any(CH.get(ids[sp]).get("ghost") is not None and sp not in disguised for sp in speakers):
                world["flicker"] = [[1.6, 2.8]]             # the lamps fail when the ghost is in the carriage
        elif ride_kind:
            vehicles.append({"id": "ride", "kind": ride_kind, "x": -600, "z": 0.0})
            for k, sp in enumerate(speakers):
                beats.append({"who": ids[sp], "ride": "ride", "seat": k + 1, "with_prev": True})
            beats.append({"vehicle": "ride", "drive_to": 3700, "sec": "end", "background": True,
                          "shot": {"type": "track", "who": "ride"}})
        elif loc == "station":
            vehicles.append({"id": "train", "kind": "train", "x": -5200, "cars": 3, "lane": "tracks"})
            beats.append({"vehicle": "train", "drive_to": 1600, "sec": 5.0, "with_prev": True})
        elif loc == "city_street":
            vehicles.append({"id": "tram", "kind": "tram", "x": -1500, "z": 0.45})
            beats.append({"vehicle": "tram", "drive_to": 4700, "sec": 9.0, "with_prev": True, "shot": "establish"})
        elif loc == "village_road":
            vehicles.append({"id": "toto", "kind": "toto", "x": 4300, "z": 0.4, "facing": -1})
            beats.append({"vehicle": "toto", "drive_to": -900, "sec": 7.0, "with_prev": True, "shot": "establish"})
        last = None
        n_lines = {sp: sum(1 for ln in lines if ln.get("speaker") == sp) for sp in change_here}
        said = {sp: 0 for sp in change_here}
        for ln in lines:
            sp = ln.get("speaker")
            text = ln["text"].strip()
            raw = str(ln.get("emotion") or "").lower()
            if sp not in ids:
                beats.append({"narrate": text, "shot_type": "wide"})
                continue
            actor = ids[sp]
            if sp in change_here:                           # the change: before its last line (or after its only one)
                said[sp] += 1
                if n_lines[sp] >= 2 and said[sp] == n_lines[sp]:
                    beats.append({"who": actor, "transform": True})
                    disguised.discard(sp)
                    revealed.add(sp)
            is_ghost = CH.get(actor).get("ghost") is not None and sp not in disguised
            emo = (GHOST_EMO.get(raw) if is_ghost else None) or EMO.get(raw) or ("scared" if raw in GHOST_EMO else None)
            if is_ghost and actor not in ghosts_seen:
                ghosts_seen.add(actor)
                if loc == "ghar":
                    world["door_open_at"] = 1.2                 # the door opens before the ghost is there
            to = last if last and last != actor else next((ids[o] for o in speakers if ids[o] != actor), None)
            b = {"who": actor, "say": text, "to": to}
            if emo:
                b["emotion"] = emo
            beats.append(b)
            last = actor
            if sp in change_here and n_lines[sp] == 1 and sp not in revealed:
                beats.append({"who": actor, "transform": True})
                disguised.discard(sp)
                revealed.add(sp)
        beats.append({"pause": 0.9})
        if not cast_spec:                                   # a scene with only narration: an empty place
            cast_spec = []
        scenes.append({"location": loc, "fps": 24, "aspect": aspect, "subtitles": True, "world": world,
                       "cast": cast_spec, "vehicles": vehicles, "beats": beats, "story_place": place})
    return {"title": story.get("title", ""), "fade": 0.6, "scenes": scenes,
            "cast": {k: {"actor": v[0], "shown": v[1]} for k, v in cast.items()}}


def latest_story(path=None, key=None):
    path = path or os.path.join(ROOT, "assets", "today_scripts.json")
    d = json.load(open(path, encoding="utf-8"))
    k = key if key in d else sorted(d)[-1]
    return k, d[k]["story"]
