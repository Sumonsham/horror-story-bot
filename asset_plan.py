"""ASSET PLAN - which pieces THIS character needs (not one fixed list for everybody).

The character's design (from the story) decides its archetype and its pieces:
  man_trousers   torso, arm, legs                                   (a shirt / kurta and trousers)
  man_dhoti      torso, arm, legs (the dhoti as cloth legs)
  bare_chest     torso (bare / loincloth), arm, legs
  saree_woman    blouse torso, arm, SKIRT (the saree from the waist to the feet), PALLU (the loose end hanging
                 from the shoulder), feet; + back hair if the hair is long / in a bun with a long braid
  long_dress     torso, arm, SKIRT (the long dress / robe), feet
  ghost_flowing  torso, arm (often long sleeves), FLOWING SKIRT (no feet, a trailing hem), BACK HAIR (long open
                 hair) - it floats; no legs at all
  child          the same pieces as its clothes say, with a child's proportions (bigger head, shorter body)
Extras by the look: long open hair -> HAIR_BACK piece (behind the body, swaying); wide / complex sleeves -> the arm
piece is allowed to be wide; a shawl -> drawn with the torso (it moves with it).
Every plan also has: the full-body reference + heads (front, three-quarter, profile, scared) and the LAYER ORDER
the renderer uses, so garments always cover what they cover in real life (a saree over the legs, the pallu over
the torso, long hair behind the back, the near arm in front).
"""

HEADS = ("three_q", "front", "profile", "scared")


def archetype(design):
    d = design or {}
    if d.get("ghost") and (d.get("sari") or d.get("robe") or d.get("hair_style") == "open_long"):
        return "ghost_flowing"
    if d.get("sari"):
        return "saree_woman"
    if d.get("robe"):
        return "long_dress"
    if d.get("dhoti"):
        return "man_dhoti"
    if d.get("sleeve") == "none":
        return "bare_chest"
    return "man_trousers"


def plan(design):
    d = design or {}
    arch = archetype(d)
    pieces = {"man_trousers": ["torso", "arm", "legs"], "man_dhoti": ["torso", "arm", "legs"],
              "bare_chest": ["torso", "arm", "legs"], "saree_woman": ["torso", "arm", "skirt", "pallu"],
              "long_dress": ["torso", "arm", "skirt"], "ghost_flowing": ["torso", "arm", "skirt"]}[arch]
    if d.get("hair_style") in ("open_long", "long"):
        pieces.append("hair_back")
    child = bool(d.get("child")) or d.get("height", 1.0) < 0.8
    feet = arch in ("saree_woman", "long_dress")
    layers = (["hair_back", "uarm_far", "farm_far", "shin_far", "thigh_far", "shin_near", "thigh_near", "skirt_lo",
               "skirt_up", "torso", "pallu", "head", "uarm_near", "farm_near"])
    return {"archetype": arch, "pieces": pieces, "heads": list(HEADS), "child": child, "feet_from_skirt": feet,
            "floats": arch == "ghost_flowing", "layers": layers, "wide_sleeves": bool(d.get("robe") or d.get("ghost")),
            "head_fraction": (0.18, 0.40) if child else (0.10, 0.33)}
