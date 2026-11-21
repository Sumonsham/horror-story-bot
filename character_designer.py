"""CHARACTER DESIGNER (the 4th assistant) - role: build every character EXACTLY as the story describes them.

Reads each character of the story (name, gender, age, kind = human / ghost, and the English "look" the writer
gives: age, face, hair, skin, clothes with colours, one special detail) and turns it into a cartoon design:
skin tone, hair style + colour, beard / moustache, glasses, tilak, clothes (kurta / panjabi / shirt / checked shirt
/ saree with its border / dhoti / trousers / robe / loincloth), their colours, shawl, beads, bangles, build
(thin / chubby), height, what they carry (lantern, torch, staff).
A GHOST is drawn as a ghost: pale or dark as written, glowing eyes in dark sockets (red if the story says red
eyes), open hair falling over the face if written, see-through, floating above the ground, a faint mist; a
shadow-only ghost ("only a dark shape") stays a faceless shadow.
The same character always gets the same design (a story's text never changes in the middle).
Gemini (the lite model, its own free limit) may read the look; the offline rules read it otherwise - both
are written into the report with the words that decided every detail ("evidence").
"""
import json
import re

import cartoon_rig as R

COLORS = {"white": (228, 230, 232), "cream": (196, 222, 236), "off-white": (210, 222, 230), "black": (34, 32, 36),
          "grey": (130, 132, 136), "gray": (130, 132, 136), "red": (40, 40, 180), "deep red": (30, 28, 140),
          "blood-red": (24, 20, 150), "maroon": (40, 30, 110), "saffron": (40, 130, 230), "orange": (30, 120, 220),
          "yellow": (60, 190, 230), "green": (60, 130, 60), "blue": (150, 96, 52), "navy": (100, 50, 30),
          "brown": (40, 70, 110), "khaki": (100, 150, 170), "pink": (150, 120, 220), "purple": (120, 60, 120),
          "gold": (40, 170, 220), "silver": (190, 192, 196)}
SKIN = {"fair": (125, 165, 212), "pale": (196, 206, 214), "wheat": (98, 136, 182), "dark": (64, 94, 132),
        "very dark": (50, 72, 102)}
HAIR = {"black": (22, 22, 26), "grey": (150, 154, 160), "gray": (150, 154, 160), "white": (225, 228, 230),
        "half-grey": (98, 100, 106), "grey-black": (70, 72, 78), "salt": (150, 154, 160)}
CLOTH_WORDS = r"(kurta|panjabi|punjabi|shirt|saree|sari|dhoti|lungi|trousers|pants|jeans|shawl|robe|dress|blouse|loincloth|gamchha|vest|sweater|coat|uniform|border|cloth)"


def _color_before(text, noun):
    """'yellow checked shirt' -> yellow; the nearest colour word just before the clothing word"""
    m = re.search(r"((?:[a-z-]+\s+){0,3})" + noun, text)
    if not m:
        return None
    words = m.group(1).split()
    for n in (2, 1):
        for i in range(len(words) - n, -1, -1):
            w = " ".join(words[i:i + n])
            if w in COLORS:
                return COLORS[w]
    return None


def offline(c):
    """one story character -> (design dict, evidence list)"""
    look = " " + str(c.get("look", "")).lower().replace(",", " ,") + " "
    gender = str(c.get("gender", "")).lower()
    age = str(c.get("age", "")).lower() + " " + look
    ghost = str(c.get("kind", "")).lower().startswith("ghost") or bool(re.search(r"\b(ghost|spirit|pishachini|yogini|petni|shakchunni|"
                                                                              r"daini|churel|not a human)\b", look))
    female = gender.startswith("f") or bool(re.search(r"\b(woman|girl|she|her)\b", look))
    agef = str(c.get("age", "")).lower()               # the story's own age field decides first
    if agef in ("old", "young", "child", "adult"):
        old, young = agef == "old", agef in ("young", "child")
    else:
        old = bool(re.search(r"\bold (man|woman|sadhu|lady)|seventy|sixty|eighty|elderly", look))
        young = bool(re.search(r"young|twent|teen|student|boy|girl", look)) and not old
    ev = []
    if ghost and re.search(r"only a dark shape|faceless|no face", look) and not re.search(r"eyes|face is seen|hair", look):
        return dict(R.DESIGNS["shadow"], ghost=True, alpha=0.85, float=10.0), ["shadow ghost: '" + re.search(
            r"only a dark shape|shadow|faceless|no face", look).group(0) + "'"]
    base = "old_woman" if (female and old) else "woman" if female else "old_man" if old else "young_man" if young else "man"
    d = dict(R.DESIGNS[base])
    ev.append(f"{'মহিলা' if female else 'পুরুষ'}, {'বৃদ্ধ' if old else 'তরুণ' if young else 'প্রাপ্তবয়স্ক'}")
    # skin
    for word, key in (("very dark-skinned", "very dark"), ("very dark skin", "very dark"), ("dark-skinned", "dark"),
                      ("dark skin", "dark"), ("thin and dark", "dark"), ("dark complexion", "dark"), ("fair", "fair"),
                      ("glowing skin", "fair"), ("pale", "pale"), ("wheat", "wheat")):
        if word in look:
            d["skin"] = SKIN[key]
            d["skin_dark"] = R._shade(SKIN[key], 0.78)
            ev.append(f"skin: '{word.strip()}'")
            break
    # hair
    if re.search(r"\bbald\b", look):
        d["hair_style"] = "bald"
        ev.append("hair: bald")
    elif re.search(r"(loose|open|wild|long)[a-z ,-]{0,20}hair[a-z ]{0,25}(waist|knee|back|shoulder|loose)|hair (down|to (her|his) (waist|knee))|"
                   r"long open[a-z ]*hair|wild loose", look):
        d["hair_style"] = "open_long"
        ev.append("hair: long open")
    elif re.search(r"matted|tied on top|top-?knot|jata", look):
        d["hair_style"] = "topknot"
        ev.append("hair: matted, tied on top")
    elif re.search(r"\bbun\b|braid|plait", look):
        d["hair_style"] = "bun"
        ev.append("hair: bun / braid")
    elif re.search(r"side-?parted|combed", look):
        d["hair_style"] = "side_part"
        ev.append("hair: neatly combed")
    elif re.search(r"messy|tousled|unkempt|tangled", look):
        d["hair_style"] = "messy" if not female else "open_long"
        ev.append("hair: messy")
    if d.get("hair_style") == "bald" and re.search(r"\bhair\b", look) and not re.search(r"\bbald", look):
        d["hair_style"] = "short"                        # the look talks about his hair: he is not bald
        ev.append("hair: short")
    hc = re.search(r"(half-grey|grey-black|white|silver|grey|gray|black)[a-z ,-]{0,22}\bhair|hair[a-z ,-]{0,12}\b(half-grey|grey-black|white|silver|grey|gray|black)\b", look)
    if hc:
        w = hc.group(1) or hc.group(2)
        d["hair"] = HAIR.get(w, HAIR["white"] if w == "silver" else HAIR["black"])
        ev.append(f"hair colour: {w}")
    # face
    beard = re.search(r"(long|short|thick|white|grey|gray|black)?\s*(grey |white |black )?(beard|stubble)", look)
    if beard and not female:
        d["beard"] = HAIR.get((beard.group(2) or beard.group(1) or "").strip(), d.get("hair") if d["hair_style"] != "bald" else (200, 204, 208))
        d["beard_len"] = "long" if beard.group(1) == "long" else "short"
        if beard.group(3) == "stubble":                 # stubble: the skin, tinted with the stubble's colour
            sc = HAIR.get((beard.group(2) or beard.group(1) or "black").strip(), HAIR["black"])
            d["beard"] = tuple(int(0.55 * a + 0.45 * b) for a, b in zip(d["skin"], sc))
        ev.append(f"beard: '{beard.group(0).strip()}'")
    elif not female and "clean-shaven" in look:
        d["beard"] = None
    if re.search(r"moustache|mustache", look) and not female:
        d["moustache"] = d.get("hair") if d["hair_style"] != "bald" else (180, 184, 188)
        d["moustache_thick"] = "thin" not in look and "light" not in look
        ev.append("moustache")
    elif base in ("man", "young_man") and not re.search(r"moustache|mustache", look):
        d["moustache"] = None
    if re.search(r"glasses|spectacles", look):
        gl = re.search(r"(brass|gold|black|silver|round)[a-z -]*(glasses|spectacles)", look)
        d["glasses"] = (40, 150, 190) if gl and gl.group(1) in ("brass", "gold") else (30, 30, 34)
        ev.append("glasses")
    if re.search(r"tilak|vermilion|sindoor|red mark|red dot", look):
        d["tilak"] = (30, 30, 190)
        ev.append("tilak / sindoor")
    # clothes
    if re.search(r"unlike any[a-z ]*saree|ancient-looking dress|\brobe\b|\bgown\b", look):
        d["robe"] = True
        col = _color_before(look, r"(robe|dress|cloth|gown)")
        if col:
            d["lower"] = d["shirt"] = col
            d["shirt_dark"] = R._shade(col, 0.78)
        b = re.search(r"([a-z-]+) and ([a-z-]+) cloth", look)
        if b and b.group(1) in COLORS and b.group(2) in COLORS:
            d["lower"] = d["shirt"] = COLORS[b.group(1)] if b.group(1) != "deep" else COLORS["deep red"]
            d["border"] = COLORS[b.group(2)]
        ev.append("long robe / ancient dress")
    elif re.search(r"\b(saree|sari)\b", look):
        d["sari"] = True
        col = _color_before(look, r"(saree|sari)")
        two = re.search(r"([a-z]+)-and-([a-z]+) (saree|sari)", look)
        if two and two.group(1) in COLORS:
            col = COLORS[two.group(1)]
            d["border"] = COLORS.get(two.group(2))
        if col:
            d["lower"] = d["shirt"] = col
            d["shirt_dark"] = R._shade(col, 0.78)
        b = re.search(r"([a-z-]+(?: [a-z-]+)?) border", look)
        if b and b.group(1).split()[-1] in COLORS or (b and b.group(1) in COLORS):
            d["border"] = COLORS.get(b.group(1), COLORS.get(b.group(1).split()[-1]))
        ev.append(f"saree{'' if not col else ' (রং লেখা আছে)'}{' + border' if d.get('border') else ''}")
    else:
        for noun, label in (("(kurta|panjabi|punjabi)", "kurta"), ("shirt", "shirt"), ("vest|sweater|coat|uniform", "upper")):
            if re.search(noun, look):
                col = _color_before(look, noun)
                if col:
                    d["shirt"], d["shirt_dark"] = col, R._shade(col, 0.78)
                d["hem"] = 52 if label == "kurta" else 22
                d["sleeve"] = "half" if "half-sleeve" in look or "half sleeve" in look else ("long" if label == "kurta" else "elbow")
                if "checked" in look or "check " in look:
                    d["checks"] = True
                ev.append(label + (" + checks" if d.get("checks") else ""))
                break
        else:
            if re.search(r"loincloth|bare[- ]chested|ash on his body", look):
                d["shirt"], d["shirt_dark"], d["sleeve"], d["hem"] = d["skin"], d["skin_dark"], "none", 8
                ev.append("bare upper body")
        if re.search(r"dhoti|lungi|loincloth", look):
            d["dhoti"] = True
            col = _color_before(look, r"(dhoti|lungi|loincloth)")
            d["lower"] = col or COLORS["white"]
            ev.append("dhoti")
        elif re.search(r"jeans|trousers|pants", look):
            col = _color_before(look, r"(jeans|trousers|pants)")
            d["lower"] = col or ((140, 90, 50) if "jeans" in look else (90, 90, 96))
            ev.append("trousers")
    if re.search(r"shawl|chadar|stole", look):
        col = _color_before(look, r"(shawl|chadar|stole)")
        d["shawl"] = col or (60, 70, 90)
        ev.append("shawl")
    elif not re.search(r"shawl", look) and base == "old_man":
        d["shawl"] = None
    if re.search(r"rudraksha|mala|beads", look):
        d["beads"] = True
        ev.append("mala")
    if re.search(r"bangles|churi", look):
        d["bangles"] = (40, 170, 220) if "gold" in look else (220, 224, 226)
        ev.append("bangles")
    # body
    if re.search(r"chubby|\bfat\b|plump|heavy-set|heavyset|stout", look):
        d["build"] = 1.22
        ev.append("build: chubby")
    elif re.search(r"\b(thin|lean|slim|skinny|bony)\b", look):
        d["build"] = 0.86
        ev.append("build: thin")
    if re.search(r"very tall", look):
        d["height"] = 1.12
    elif re.search(r"\btall\b", look):
        d["height"] = 1.07
    elif re.search(r"\bshort\b(?! hair| grey| beard| black)", look):
        d["height"] = 0.92
    bag = re.search(r"(sling|shoulder|cloth|jhola|jute)?[a-z -]{0,10}\bbag\b", look)
    if bag:
        d["bag"] = _color_before(look, r"bag") or (70, 110, 140)
        ev.append("bag")
    if re.search(r"flower in (her|his) hair|hair[a-z ]{0,25}flower|flower[a-z ]{0,10}hair", look):
        fl = re.search(r"(red|white|yellow|pink) flower", look)
        d["flower"] = COLORS.get(fl.group(1) if fl else "red")
        ev.append("flower in the hair")
    if re.search(r"necklace|gold ornaments|ornaments|jewel|chain", look):
        d["necklace"] = (40, 170, 220) if not re.search(r"bone", look) else (200, 210, 214)
        ev.append("necklace / ornaments")
    if re.search(r"earring|ear-ring", look):
        d["earrings"] = (40, 170, 220)
        ev.append("earrings")
    if re.search(r"kohl|kajal|kajol", look):
        d["kohl"] = True
        ev.append("kohl")
    for w in ("lantern", "torch", "staff"):
        if re.search(rf"(carries|carrying|holding|holds|with|always)[a-z ,]{{0,30}}{w}|{w} in (his|her) hand", look):
            d["carry"] = w
            ev.append(f"carries a {w}")
            break
    if str(c.get("age", "")).lower() == "child" or re.search(r"\b(child|kid|little (boy|girl)|aged? (about )?([4-9]|1[0-2])\b|"
                                                                r"(four|five|six|seven|eight|nine|ten|eleven|twelve)[- ]year)", look):
        d.update(child=True, height=0.72, build=0.86, beard=None, moustache=None)
        ev.append("child: smaller body, bigger head")
    if ghost:
        d.update(ghost=True, alpha=0.78, float=16.0, ink=(60, 40, 50))
        eyes = re.search(r"(red|burning|glowing|white|yellow|green|large calm dark)[a-z ]*eyes", look)
        d["glow_eyes"] = {"red": (40, 40, 240), "burning": (40, 60, 245), "green": (90, 230, 90),
                          "yellow": (80, 230, 250)}.get(eyes.group(1) if eyes else "", (210, 240, 250))
        if eyes and eyes.group(1) == "large calm dark":
            d["glow_eyes"] = None                         # a beautiful yogini with calm human eyes stays so
        if "pale" in look or ("dark" not in look and "fair" not in look):
            d["pale"] = True
            d["skin"], d["skin_dark"] = SKIN["pale"], R._shade(SKIN["pale"], 0.8)
        d["mist"] = bool(re.search(r"mist|smoke|glow", look)) or True
        ev.append("ghost: see-through, floating" + (", glowing eyes" if d.get("glow_eyes") else ""))
    return d, ev


PROMPT = """You turn a horror-story character's description into a cartoon design. Answer JSON only:
{{"skin":"fair|wheat|dark|very dark|pale","hair_style":"bald|short|side_part|messy|topknot|bun|long|open_long",
"hair_color":"black|grey|white|half-grey|grey-black","beard":"none|short|long|stubble","moustache":"none|thin|thick",
"glasses":true|false,"tilak":true|false,"upper":"kurta|shirt|checked shirt|saree|robe|bare|other","upper_color":"<colour word>",
"lower":"dhoti|trousers|jeans|saree|robe","lower_color":"<colour word>","border_color":"<colour or none>","shawl_color":"<colour or none>",
"beads":true|false,"bangles":true|false,"build":"thin|normal|chubby","height":"short|normal|tall|very tall",
"carry":"none|lantern|torch|staff","ghost_eyes":"none|white|red|yellow|green","shadow_only":true|false}}
Use ONLY what the description says (no guessing). Character: name {name}, gender {gender}, age {age}, kind {kind}.
Description: {look}"""


def design(c, llm=None):
    """the design of one story character: (design, evidence, source). Gemini fills only what the offline reading
    could not decide; the offline reading is always the base (nothing invented)."""
    d, ev = offline(c)
    if not llm or d.get("faceless"):
        return d, ev, "offline-rules"
    try:
        raw = llm(PROMPT.format(name=c.get("name"), gender=c.get("gender"), age=c.get("age"), kind=c.get("kind"),
                                look=str(c.get("look", ""))[:600]))
        g = json.loads(raw[raw.find("{"):raw.rfind("}") + 1]) if raw else None
    except Exception:
        g = None
    if not g:
        return d, ev, "offline-rules"
    look = str(c.get("look", "")).lower()

    def said(*words):                                   # Gemini's answer counts only if the look has the word
        return any(w and w.split()[0] in look for w in words)
    if g.get("upper_color") in COLORS and said(g["upper_color"]):
        d["shirt"], d["shirt_dark"] = COLORS[g["upper_color"]], R._shade(COLORS[g["upper_color"]], 0.78)
        if d.get("sari") or d.get("robe"):
            d["lower"] = d["shirt"]
    if g.get("lower_color") in COLORS and said(g["lower_color"]) and not (d.get("sari") or d.get("robe")):
        d["lower"] = COLORS[g["lower_color"]]
    if g.get("border_color") in COLORS and said(g["border_color"]):
        d["border"] = COLORS[g["border_color"]]
    if g.get("carry") in ("lantern", "torch", "staff") and said(g["carry"]):
        d["carry"] = g["carry"]
    ev.append("Gemini: রং / জিনিস মিলিয়ে দেখেছে (শুধু লেখায় থাকা শব্দ নেওয়া হয়েছে)")
    return d, ev, "gemini+rules"


def _key(c):
    import hashlib
    return hashlib.sha1(f"{str(c.get('name', '')).strip().lower()}|{str(c.get('look', '')).strip()}".encode()).hexdigest()[:12]


def _plain(d):
    return {k: (list(v) if isinstance(v, tuple) else v) for k, v in d.items()}


def _typed(d):
    return {k: (tuple(v) if isinstance(v, list) else v) for k, v in d.items()}


def design_cast(chars, llm=None, library=None, log=print):
    """every character of a story -> {name: {"design", "evidence", "source"}}. The library (a JSON file kept in
    the repo) remembers every design by name + look: a series character (Taranath, Bhairab...) with the same
    look gets the SAME design in every episode; a new person gets a new design and is remembered too."""
    lib = {}
    if library:
        try:
            lib = json.load(open(library, encoding="utf-8"))
        except Exception:
            lib = {}
    out, new = {}, 0
    for c in chars or []:
        if not isinstance(c, dict) or not c.get("name"):
            continue
        k = _key(c)
        if k in lib:
            rec = lib[k]
        else:
            d, ev, src = design(c, llm)
            rec = {"name": c["name"], "look": str(c.get("look", ""))[:600], "design": _plain(d), "evidence": ev, "source": src,
                   "audit": audit(c, ev)}
            lib[k] = rec
            new += 1
        out[str(c["name"])] = rec
    if library and new:
        import os
        os.makedirs(os.path.dirname(os.path.abspath(library)), exist_ok=True)
        with open(library, "w", encoding="utf-8") as f:
            json.dump(lib, f, ensure_ascii=False, indent=1)
    log(f"  character designer: {len(out)} characters ({new} new, {len(out) - new} from the library)")
    return out


# =========================================================== the STRICT check: nothing of the look is lost silently
DRAWN = [r"\b(man|woman|boy|girl|person|lady|figure|yogini|spirit|sadhu|astrologer|tantrik|student|shopkeeper|madwoman|nephew)\b",
         r"of about|years? old|\bage", r"skin|dark|fair|pale|complexion", r"hair|bald|bun|braid|matted|top", r"beard|stubble|moustache|mustache",
         r"glasses|spectacles", r"tilak|vermilion|sindoor|red mark", r"saree|sari|robe|dress|cloth|gown", r"kurta|panjabi|punjabi|shirt|vest",
         r"dhoti|lungi|loincloth|trousers|jeans|pants", r"border", r"shawl|chadar|stole", r"rudraksha|mala|beads", r"bangles",
         r"chubby|fat|plump|thin|lean|slim|skinny|tall|short\b", r"lantern|torch|staff", r"\beyes?\b", r"bag", r"flower",
         r"necklace|ornament|jewel|chain", r"earring", r"kohl|kajal", r"ghost|spirit|not a human|mist|smoke|shadow",
         r"face|bare feet|feet|barefoot"]


def audit(c, evidence):
    """every detail phrase of the look -> drawn / not drawn (the report lists what the cartoon can not show yet)"""
    look = str(c.get("look", ""))
    phrases = [p.strip(" .") for p in re.split(r"[,;:()]| and | with | who ", look) if len(p.strip(" .")) > 2]
    drawn, not_drawn, not_look = [], [], []
    names = [str(c.get(k, "")).lower() for k in ("name", "name_local") if c.get(k)]
    for ph in phrases:
        low = ph.lower()
        if any(n and (n in low or low in n) for n in names) or re.fullmatch(r"(the )?[A-Z][\w -]*", ph):
            continue                                       # just the name
        if re.search(r"fragrance|smell|laugh|knows|voice|listening|sitting|standing|room|forest|temple|tree|kolkata|"
                     r"\d{4}s|presence|says|calm|nervous|curious|wild-eyed|always|never|seen only", low) and \
                not any(re.search(p, low) for p in DRAWN[3:]):
            not_look.append(ph)                            # behaviour / place / smell - not how the person looks
            continue
        (drawn if any(re.search(p, low) for p in DRAWN) else not_drawn).append(ph)
    missing = [f for f in ("gender", "age", "kind", "look") if not c.get(f)]
    return {"drawn": drawn, "not_drawn": not_drawn, "not_appearance": not_look, "missing_fields": missing,
            "complete": not missing and not not_drawn}


ENRICH = """You are the STRICT CHARACTER ASSISTANT of a Bengali horror cartoon. Below is a whole story and its characters.
For EVERY character, collect EVERY visible detail the STORY TEXT itself gives about how they look (clothes, colours,
hair, face, body, what they carry, ornaments, how a ghost looks) that is NOT already in their look. Copy the exact
words from the story as "quote" (they must be found in the text) and give a short English "detail".
Answer JSON: {{"characters":[{{"name":"<name>","details":[{{"quote":"<exact words from the story>","detail":"<English>"}}]}}]}}
Characters: {chars}
Story: {story}"""


def enrich_from_story(story, llm=None, log=print):
    """the strict assistant reads the WHOLE story (not only the look line): every extra detail it finds is added
    to the look - but only if its quote really is in the story (nothing invented). Returns {name: [details]}"""
    chars = [c for c in (story.get("characters") or []) if isinstance(c, dict) and c.get("name")]
    if not llm or not chars:
        return {}
    text = " ".join(str(ln.get("text", "")) + " " + str(ln.get("en", "")) for sc in story.get("scenes") or []
                    for ln in (sc.get("lines") or []) if isinstance(ln, dict))
    text += " " + " ".join(str(sc.get("place", "")) + " " + str(sc.get("action", "")) for sc in story.get("scenes") or [])
    try:
        raw = llm(ENRICH.format(chars=json.dumps([{k: c.get(k) for k in ("name", "name_local", "kind", "look")} for c in chars],
                                                 ensure_ascii=False)[:3000], story=text[:24000]))
        data = json.loads(raw[raw.find("{"):raw.rfind("}") + 1]) if raw else {}
    except Exception as e:
        log(f"  strict character assistant: no usable answer ({str(e)[:80]})")
        return {}
    import unicodedata
    norm = lambda x: re.sub(r"[\W_]+", "", unicodedata.normalize("NFD", str(x)).lower(), flags=re.U)
    T = norm(text)
    found = {}
    for g in data.get("characters", []) or []:
        c = next((c for c in chars if str(c["name"]).lower() == str(g.get("name", "")).lower()), None)
        if not c:
            continue
        keep = [d_ for d_ in g.get("details", []) or [] if d_.get("quote") and norm(d_["quote"]) and norm(d_["quote"]) in T
                and d_.get("detail")]
        if keep:
            c["look"] = (str(c.get("look", "")).rstrip(". ") + ", " + ", ".join(str(d_["detail"]) for d_ in keep[:6])).strip(", ")
            found[c["name"]] = [f"{d_['detail']} (\"{d_['quote']}\")" for d_ in keep[:6]]
    log(f"  strict character assistant: {sum(len(v) for v in found.values())} more details found in the story text")
    return found
