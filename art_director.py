"""ART DIRECTOR - one consistent Bengali 2.5D TV-cartoon art direction for EVERY generated picture.

Every prompt for a character part or a background plate is built here, so the whole channel has one look:
flat 2D cartoon colours, clean bold dark outlines, soft cel shading, natural body proportions, Bengali people and
places. Characters are drawn alone on a plain light-grey studio background (so they can be cut out exactly);
backgrounds are drawn EMPTY (no people) with the ground in the lower part (where the characters will stand).
"""
STYLE = ("flat 2D Bengali television cartoon illustration, clean bold dark outlines, soft cel shading, rich but "
         "gentle colours, natural human anatomy and proportions, expressive friendly cartoon face, high quality "
         "professional animation character art")
BG_STYLE = ("flat 2D Bengali television cartoon background painting, clean outlines, soft painted shading, "
            "atmospheric night lighting, detailed professional animation background art")
STUDIO = ("plain flat light grey background (#b4b4b4), no shadow on the background, no floor line, no text, no logo, "
          "no frame, nothing else in the picture")
BG_KEY = (180, 180, 180)

POSE_BODY = ("ONE single full-body character standing straight, seen in three-quarter view turned slightly towards the "
             "RIGHT side of the picture, BOTH arms held out away from the body at about 30 degrees (an A-pose) so that "
             "there is clear background between each arm and the body from the armpit down to the hand, hands open and "
             "relaxed and empty, legs slightly apart with a clear gap between the legs and between the feet, both feet "
             "flat and fully visible, NOTHING in the hands and nothing next to the body (no lantern, no bag, no stick, no "
             "furniture, no props), no shadow on the ground, the whole body inside the picture with wide empty margins "
             "all round (the head and the feet well away from the edges), neutral calm face, mouth closed")
HEAD_VIEWS = {
    "front": "the head and neck only, seen straight from the FRONT, looking at the viewer",
    "three_q": "the head and neck only, in three-quarter view turned towards the RIGHT side of the picture",
    "profile": "the head and neck only, in full side PROFILE facing the RIGHT side of the picture",
    "scared": "the head and neck only, in three-quarter view turned towards the RIGHT, a frightened face: wide eyes, "
              "raised eyebrows, mouth slightly open",
}
GHOST = ("a supernatural ghost, eerie but not gory, pale ghostly skin colours, long hair falling BEHIND the shoulders "
         "and down the back (never over the arms), NO glow, NO mist, NO aura, NO smoke around the figure (the animation "
         "adds them later), a clean dark outline all round, feet visible")
PLACES = {
    "pond": "a quiet village pond (pukur) at night, old trees on the bank, a full moon reflected in the dark water, a "
            "muddy bank with grass in the foreground",
    "road": "a lonely village road at night stretching to the horizon, electric poles with wires, a dim street lamp, "
            "a closed small roadside tea shop with a tin roof, trees beside the road",
    "jungle": "a dense dark Bengal forest at night, tall sal trees, a narrow winding dirt path through the middle, "
              "fog between the trunks, moonlight through the leaves",
    "house_interior": "inside a poor old Bengali village hut at night, mud walls, bamboo rafters, a small barred "
                      "window, a wooden door, a reed mat on the earthen floor, an oil lamp in a wall niche",
    "railway_station": "a small deserted Bengal railway station at night, an empty platform with a yellow line, a "
                       "tin-roofed shed on pillars, a hanging bulb, a bench, railway tracks, a red signal light far away",
    "cremation_ground": "an old cremation ground (shmashan) beside a river at night, a burning wooden pyre, ghat "
                        "steps, a twisted bare tree, a small temple far away, smoke in the air",
    "rajbari": "a ruined old Bengal zamindar palace (rajbari) at night, broken pillars and arched windows, creepers on "
               "the walls, a weed-grown courtyard in front, one dimly lit window",
}


def character_prompt(rec):
    """full-body prompt from the character designer's record (name, look, design)"""
    look = str(rec.get("look", "")).strip().rstrip(".")
    d = rec.get("design") or {}
    who = ("a " + ("ghost " if d.get("ghost") else "") + ("woman" if d.get("sari") or d.get("robe") else "man"))
    ghost = (" " + GHOST + ".") if d.get("ghost") else ""
    return f"{STYLE}. {POSE_BODY}. The character: {who} - {look}.{ghost} {STUDIO}."


def head_prompt(rec, view):
    look = str(rec.get("look", "")).strip().rstrip(".")
    return (f"{STYLE}. Use image 0 ONLY to keep EXACTLY the same character (same face, hair, skin, beard, ornaments, "
            f"clothes colours at the neck). Draw {HEAD_VIEWS[view]}, large and centred, the neck ending at the bottom "
            f"edge of the picture. The character: {look}. {STUDIO}.")


def plate_prompt(loc, weather=None):
    w = weather or {}
    sky = " heavy rain falling, storm clouds," if w.get("rain") else ""
    return (f"{BG_STYLE}. A wide establishing view of {PLACES.get(loc, loc)},{sky} completely EMPTY - no people, no "
            f"animals, no characters, no text. The ground or floor fills the lower 40 percent of the picture, the horizon "
            f"a little below the middle, open space in the middle foreground where people could stand.")


PIECE = ("like a separate cut-out paper-puppet piece for animation, clean outline all round, nothing else attached, "
         "centred with empty space around it")


def part_prompt(rec, part):
    """one separate body part of the SAME character (image 0 = its full-body reference)"""
    look = str(rec.get("look", "")).strip().rstrip(".")
    keep = ("Use image 0 ONLY to keep EXACTLY the same character: the same clothes, colours, patterns, skin and "
            "ornaments. ")
    what = {
        "torso": ("Draw ONLY the clothed TORSO of this character - from the base of the neck down to the hips - in "
                  "three-quarter view turned towards the RIGHT, WITHOUT the head, WITHOUT any arms (clean rounded "
                  "shoulders where the arms would join), WITHOUT legs"),
        "arm": ("Draw ONLY ONE ARM of this character - from the shoulder to the fingertips, with the same sleeve and "
                "skin - hanging STRAIGHT DOWN vertically, slightly bent at nothing, the hand open and relaxed, "
                "fingers together"),
        "legs": ("Draw ONLY the LOWER BODY of this character - from the waist down, with the same lower clothes and "
                 "footwear - standing, three-quarter view turned towards the RIGHT, the two legs slightly apart with a "
                 "clear gap between them, both feet flat"),
        "skirt": ("Draw ONLY the LOWER GARMENT of this character from the waist down to the ground - the saree's "
                  "pleated lower drape / the long dress / the robe, exactly the same fabric, colour, print and border - "
                  "with the bare feet or footwear just showing below the hem, standing, three-quarter view turned towards "
                  "the RIGHT"),
        "pallu": ("Draw ONLY the loose decorated END of this character's saree (the aanchal / pallu) as it hangs from the "
                  "shoulder down the back, the same fabric, colour, print and border, gently flowing"),
        "hair_back": ("Draw ONLY the BACK PART of this character's long hair as it falls behind the head down the back - "
                      "the same colour and style - NO face, NO head, NO body"),
    }[part]
    if part == "skirt" and (rec.get("design") or {}).get("ghost"):
        what = ("Draw ONLY the flowing ghostly LOWER GARMENT of this character from the waist down - the same fabric and "
                "colour - ending in a soft trailing, wispy hem with NO feet, as if floating")
    return f"{STYLE}. {keep}{what}, {PIECE}. The character: {look}. {STUDIO}."
