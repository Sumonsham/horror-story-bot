"""LOCATION LIBRARY - every place the story can happen in, drawn by code (zero cost, nothing downloaded).

Seven places (more can be added the same way - write one painter + one entry in LOCATIONS):
  pond              গ্রামের পুকুরপাড়      live water, moon reflection, ripples, mist, logs to sit on
  road              রাতের রাস্তা           asphalt road to the horizon, centre dashes, electric poles + wires,
                                            a flickering street lamp, a closed roadside shop
  jungle            জঙ্গল                 dense trunks, canopy, a winding dirt path, thick fog, many fireflies
  house_interior    ঘরের ভেতর / কুটির      mud wall, rafters, a window (rain + lightning outside), a wooden door
                                            that can be knocked and opened, a reed mat, an oil lamp (pradip)
  railway_station   রেলস্টেশন             platform with its yellow line, rails + sleepers, a shed roof on pillars,
                                            a hanging bulb that flickers, a bench, a blinking red signal
  cremation_ground  শ্মশান                river (live water), a burning pyre (fire, sparks, rising smoke), a bare
                                            twisted tree, broken pots, ghat steps, a small temple far away
  rajbari           পুরোনো রাজবাড়ি        a ruined palace: arched windows (one dimly lit), columns, broken
                                            parapet, creepers, steps, a stone courtyard, bats

Each place gives: the environment spec, spots (where people stand / enter / exit), what can be sat on, what moves
by itself, the light sources, and its ambience. The renderer asks this module for everything place-specific.
"""
import math

import cv2
import numpy as np

HORIZON = 545
W, H = 1920, 1080

LOCATIONS = {
    "pond": {"bn": "গ্রামের পুকুরপাড়", "outdoor": True, "seat": "log",
             "spots": {"a": (790, 935), "b": (1075, 935), "c": (560, 935), "enter_from": (-160, 935), "exit_to": (-220, 935),
                       "focus": (1440, 560), "door": None},
             "features": ["water", "moon", "trees", "fireflies", "mist"], "ambience": ["wind", "crickets", "water"]},
    "road": {"bn": "রাতের রাস্তা", "outdoor": True, "seat": None,
             "spots": {"a": (900, 935), "b": (1160, 935), "c": (600, 935), "enter_from": (2120, 935), "exit_to": (-220, 935),
                       "focus": (960, 600), "door": None},
             "features": ["road", "street_lamp", "poles", "shop", "trees"], "ambience": ["wind", "crickets", "far_traffic"]},
    "jungle": {"bn": "জঙ্গল", "outdoor": True, "seat": None,
               "spots": {"a": (820, 935), "b": (1090, 935), "c": (600, 935), "enter_from": (-160, 935), "exit_to": (2120, 935),
                         "focus": (1300, 560), "door": None},
               "features": ["dense_trees", "path", "fog", "fireflies"], "ambience": ["wind", "crickets", "owl"]},
    "house_interior": {"bn": "ঘরের ভেতর / কুটির", "outdoor": False, "seat": "stool",
                       "spots": {"a": (840, 935), "b": (1120, 935), "c": (1380, 935), "enter_from": (360, 935),
                                 "exit_to": (360, 935), "focus": (360, 620), "door": (360, 935), "window": (1440, 410)},
                       "features": ["door", "window", "oil_lamp", "mat"], "ambience": ["room_tone", "rain_outside"]},
    "railway_station": {"bn": "রেলস্টেশন", "outdoor": True, "seat": "bench",
                        "spots": {"a": (820, 935), "b": (1090, 935), "c": (1450, 935), "enter_from": (2120, 935),
                                  "exit_to": (-220, 935), "focus": (1700, 520), "door": None},
                        "features": ["platform", "rails", "shed", "bulb", "bench", "signal"], "ambience": ["wind", "crickets", "hum"]},
    "cremation_ground": {"bn": "শ্মশান", "outdoor": True, "seat": None,
                         "spots": {"a": (760, 935), "b": (1010, 935), "c": (560, 935), "enter_from": (-160, 935),
                                   "exit_to": (-220, 935), "focus": (1360, 760), "door": None},
                         "features": ["river", "pyre_fire", "smoke", "bare_tree", "temple"], "ambience": ["fire", "wind", "water"]},
    "rajbari": {"bn": "পুরোনো রাজবাড়ি", "outdoor": True, "seat": None,
                "spots": {"a": (820, 935), "b": (1090, 935), "c": (600, 935), "enter_from": (-160, 935), "exit_to": (2120, 935),
                          "focus": (960, 380), "door": None},
                "features": ["palace", "lit_window", "bats", "courtyard"], "ambience": ["wind", "crickets", "owl"]},
}


def spec_for(loc, weather=None):
    """the environment spec of a place (+ weather: rain 0..1, lightning [times], storm)"""
    w = weather or {}
    rain, lightning = float(w.get("rain", 0.0)), list(w.get("lightning", []))
    base = {"location": loc, "moon": (1430, 175), "clouds": 3, "fireflies": 18, "falling_leaves": 10, "grass": 420,
            "bank_grass": 260, "rain": rain, "lightning": lightning, "fog": 1.0}
    if loc == "pond":
        base.update({"pond": (1110, 720, 560, 128),
                     "trees": [{"x": 250, "y": 960, "h": 760, "depth": 5, "seed": 3},
                               {"x": 1760, "y": 900, "h": 640, "depth": 5, "seed": 11},
                               {"x": 1395, "y": 586, "h": 250, "depth": 4, "seed": 21, "scale": 0.5}]})
    elif loc == "road":
        base.update({"trees": [{"x": 1820, "y": 1000, "h": 720, "depth": 5, "seed": 7},
                               {"x": 640, "y": 610, "h": 260, "depth": 4, "seed": 17, "scale": 0.5},
                               {"x": 1330, "y": 600, "h": 220, "depth": 4, "seed": 19, "scale": 0.45}],
                     "fireflies": 6, "grass": 160, "bank_grass": 120})
    elif loc == "jungle":
        base.update({"trees": [{"x": 160, "y": 1000, "h": 820, "depth": 5, "seed": 31},
                               {"x": 1780, "y": 980, "h": 760, "depth": 5, "seed": 33},
                               {"x": 520, "y": 640, "h": 420, "depth": 5, "seed": 35, "scale": 0.7},
                               {"x": 1420, "y": 630, "h": 400, "depth": 5, "seed": 37, "scale": 0.7},
                               {"x": 1060, "y": 590, "h": 260, "depth": 4, "seed": 39, "scale": 0.5}],
                     "fireflies": 34, "falling_leaves": 18, "fog": 1.5, "clouds": 1, "moon": (1500, 120)})
    elif loc == "house_interior":
        base.update({"trees": [], "fireflies": 0, "falling_leaves": 0, "grass": 0, "bank_grass": 0, "clouds": 0, "fog": 0.0,
                     "sky": False, "sky_parallax": 1.0, "outside_rain": rain or (0.8 if lightning else 0.0), "rain": 0.0, "lightning_k": 0.28})
    elif loc == "railway_station":
        base.update({"trees": [{"x": 1820, "y": 610, "h": 300, "depth": 4, "seed": 41, "scale": 0.55},
                               {"x": 120, "y": 600, "h": 260, "depth": 4, "seed": 43, "scale": 0.5}],
                     "fireflies": 4, "grass": 0, "bank_grass": 60, "falling_leaves": 4})
    elif loc == "cremation_ground":
        base.update({"pond": (960, 650, 1300, 62),
                     "trees": [{"x": 260, "y": 980, "h": 720, "depth": 5, "seed": 51, "bare": True},
                               {"x": 1820, "y": 640, "h": 320, "depth": 4, "seed": 53, "scale": 0.55}],
                     "fireflies": 0, "falling_leaves": 6, "grass": 260, "bank_grass": 120, "fog": 1.2})
    elif loc == "rajbari":
        base.update({"trees": [{"x": 140, "y": 1000, "h": 780, "depth": 5, "seed": 61},
                               {"x": 1800, "y": 960, "h": 560, "depth": 5, "seed": 63, "bare": True}],
                     "fireflies": 8, "grass": 300, "bank_grass": 200, "moon": (1650, 140)})
    if rain and LOCATIONS.get(loc, {}).get("outdoor", True):
        base["fireflies"] = 0
    return base


def grass_ok(loc, x, y):
    """no grass on a road, a platform, a floor or a river"""
    if loc == "road":
        u = (y - (HORIZON + 42)) / (H - HORIZON - 42)
        return abs(x - 960) > 40 + 760 * max(0.0, u) + 30
    if loc == "railway_station":
        return y < 600
    if loc == "house_interior":
        return False
    if loc == "cremation_ground":
        return y > 760
    return True


# ====================================================================== painters (rasters, made once)
def _noise(rng, h, w, amp):
    return (rng.standard_normal((h, w)) * amp)[..., None]


def paint(env):
    """change the base rasters (env.sky, env.far, env.land) into this place; sets env.loc_state"""
    loc = env.loc
    rng = np.random.default_rng(97)
    env.loc_state = {}
    fn = {"road": _road, "jungle": _jungle, "house_interior": _interior, "railway_station": _station,
          "cremation_ground": _cremation, "rajbari": _rajbari}.get(loc)
    if fn:
        fn(env, rng)


def _road(env, rng):
    land = env.land
    vy = HORIZON + 42
    poly = np.array([(938, vy), (982, vy), (1730, H), (190, H)], np.int32)
    m = np.zeros((H, W), np.uint8)
    cv2.fillPoly(m, [poly], 255, cv2.LINE_AA)
    asphalt = np.clip(np.full((H, W, 3), (46, 45, 48), "float32") + _noise(rng, H, W, 4.0), 0, 255).astype(np.uint8)
    a = (m.astype("float32") / 255.0)[..., None]
    land[..., :3] = (land[..., :3] * (1 - a) + asphalt * a).astype(np.uint8)
    land[..., 3] = np.maximum(land[..., 3], m)
    cv2.line(land, (938, vy), (190, H), (98, 100, 104, 255), 5, cv2.LINE_AA)       # edge lines
    cv2.line(land, (982, vy), (1730, H), (98, 100, 104, 255), 5, cv2.LINE_AA)
    for i in range(14):                                                           # centre dashes in perspective
        u0, u1 = (i / 14.0) ** 2, ((i + 0.45) / 14.0) ** 2
        y0, y1 = vy + (H - vy) * u0, vy + (H - vy) * u1
        wd = 2 + 16 * u1
        cv2.fillPoly(land, [np.array([(960 - wd / 2, y0), (960 + wd / 2, y0), (960 + wd, y1), (960 - wd, y1)], np.int32)],
                     (150, 170, 178, 255), cv2.LINE_AA)
    tops = []
    for u in (0.08, 0.2, 0.42, 0.78):                                             # electric poles + sagging wires
        y = vy + (H - vy) * u
        x = 982 + (1730 - 982) * u + 70 * u + 20
        hgt = 40 + 560 * u
        cv2.line(land, (int(x), int(y)), (int(x), int(y - hgt)), (30, 34, 40, 255), max(2, int(14 * u)), cv2.LINE_AA)
        cv2.line(land, (int(x - 40 * u), int(y - hgt + 10 * u)), (int(x + 40 * u), int(y - hgt + 10 * u)),
                 (30, 34, 40, 255), max(1, int(6 * u)), cv2.LINE_AA)
        tops.append((x, y - hgt + 10 * u))
    for (x0, y0), (x1, y1) in zip(tops, tops[1:]):
        pts = [(x0 + (x1 - x0) * s, y0 + (y1 - y0) * s + 30 * math.sin(math.pi * s) * (x1 - x0) / 300) for s in np.linspace(0, 1, 16)]
        cv2.polylines(land, [np.array(pts, np.int32)], False, (24, 26, 30, 255), 2, cv2.LINE_AA)
    # a closed roadside shop (tin roof, shutter)
    cv2.rectangle(land, (110, 620), (520, 900), (52, 62, 74, 255), -1)
    cv2.fillPoly(land, [np.array([(80, 630), (550, 630), (520, 560), (110, 560)], np.int32)], (70, 76, 84, 255), cv2.LINE_AA)
    for x in range(120, 520, 22):
        cv2.line(land, (x, 562), (x - 6, 628), (56, 60, 66, 255), 2, cv2.LINE_AA)
    cv2.rectangle(land, (170, 680), (460, 900), (64, 72, 80, 255), -1)
    for y in range(686, 900, 12):
        cv2.line(land, (172, y), (458, y), (48, 54, 60, 255), 2)
    cv2.rectangle(land, (300, 860), (330, 876), (30, 30, 34, 255), -1)           # a padlock
    env.loc_state["lamp"] = (1560, 905, 480)


def _jungle(env, rng):
    far = env.far
    for _ in range(170):                                                          # dense trunks
        x = int(rng.uniform(-20, W + 20))
        top = int(rng.uniform(40, 330))
        wd = int(rng.uniform(6, 26))
        c = int(rng.uniform(18, 30))
        cv2.line(far, (x, HORIZON + 50), (x + int(rng.uniform(-30, 30)), top), (c, c + 6, c, 255), wd, cv2.LINE_AA)
    for _ in range(90):                                                           # canopy hiding most of the sky
        x, y = int(rng.uniform(-60, W + 60)), int(rng.uniform(-40, 250))
        cv2.ellipse(far, (x, y), (int(rng.uniform(60, 170)), int(rng.uniform(40, 90))), 0, 0, 360,
                    (int(rng.uniform(18, 26)), int(rng.uniform(28, 38)), int(rng.uniform(18, 24)), 255), -1, cv2.LINE_AA)
    mx, my = env.moon                                                             # a hole in the canopy for the moon
    cv2.circle(far, (mx, my), 120, (0, 0, 0, 0), -1, cv2.LINE_AA)
    land = env.land
    pts_l, pts_r = [], []
    for k in range(30):                                                           # a winding dirt path
        u = k / 29.0
        y = HORIZON + 44 + (H - HORIZON - 44) * u ** 1.3
        cx = 1000 + 160 * math.sin(u * 3.2 + 0.6) * (1 - u * 0.4)
        wdt = 18 + 330 * u ** 1.4
        pts_l.append((cx - wdt, y))
        pts_r.append((cx + wdt, y))
    poly = np.array(pts_l + pts_r[::-1], np.int32)
    cv2.fillPoly(land, [poly], (44, 58, 70, 255), cv2.LINE_AA)
    for _ in range(400):                                                          # leaf litter
        x, y = int(rng.uniform(0, W)), int(rng.uniform(HORIZON + 60, H))
        cv2.ellipse(land, (x, y), (int(rng.uniform(3, 8)), 2), int(rng.uniform(0, 180)), 0, 360,
                    (int(rng.uniform(26, 40)), int(rng.uniform(46, 66)), int(rng.uniform(60, 90)), 255), -1, cv2.LINE_AA)


def _interior(env, rng):
    env.stars = []
    y = np.linspace(0, 1, H)[:, None, None]
    wall = (np.array([34, 44, 56], "float32") * (1 - y) + np.array([58, 76, 94], "float32") * y) * np.ones((1, W, 1), "float32")
    wall += _noise(rng, H, W, 3.0)
    blot = cv2.GaussianBlur(rng.uniform(-1, 1, (H // 20, W // 20)).astype("float32"), (0, 0), 2)
    wall += cv2.resize(blot, (W, H))[..., None] * 9                              # damp patches on the mud wall
    wall = np.clip(wall, 0, 255).astype(np.uint8)
    for _ in range(9):                                                            # cracks
        x, yy = int(rng.uniform(500, 1800)), int(rng.uniform(160, 640))
        pts = [(x, yy)]
        for _ in range(6):
            x += int(rng.uniform(-18, 18))
            yy += int(rng.uniform(8, 22))
            pts.append((x, yy))
        cv2.polylines(wall, [np.array(pts, np.int32)], False, (26, 34, 42), 2, cv2.LINE_AA)
    for yy in (36, 96):                                                           # rafters (bamboo beams)
        cv2.rectangle(wall, (0, yy), (W, yy + 22), (30, 44, 56), -1)
        cv2.line(wall, (0, yy + 4), (W, yy + 4), (52, 70, 86), 2)
    for x in (90, 1830):                                                          # wooden posts
        cv2.rectangle(wall, (x, 0), (x + 34, 740), (30, 42, 54), -1)
    wx0, wy0, wx1, wy1 = 1300, 300, 1580, 520                                     # the window (outside drawn per frame)
    cv2.rectangle(wall, (wx0 - 14, wy0 - 14), (wx1 + 14, wy1 + 14), (28, 38, 50), -1)
    cv2.rectangle(wall, (wx0, wy0), (wx1, wy1), (40, 20, 12), -1)
    dx0, dy0, dx1, dy1 = 250, 330, 470, 935                                       # the doorway
    cv2.rectangle(wall, (dx0 - 18, dy0 - 18), (dx1 + 18, dy1), (26, 36, 48), -1)
    cv2.rectangle(wall, (dx0, dy0), (dx1, dy1), (10, 8, 8), -1)
    cv2.rectangle(wall, (900, 440), (1020, 540), (24, 32, 40), -1)               # a niche for the oil lamp
    cv2.ellipse(wall, (960, 440), (60, 40), 0, 180, 360, (24, 32, 40), -1, cv2.LINE_AA)
    env.sky = wall
    env.far = np.zeros((H, W, 4), np.uint8)
    land = np.zeros((H, W, 4), np.uint8)
    g = np.linspace(0, 1, H - 720)[:, None, None]
    floor = (np.array([40, 56, 70], "float32") * (1 - g) + np.array([52, 70, 86], "float32") * g) * np.ones((1, W, 1), "float32")
    floor += _noise(rng, H - 720, W, 3.0)
    land[720:, :, :3] = np.clip(floor, 0, 255).astype(np.uint8)
    land[720:, :, 3] = 255
    cv2.line(land, (0, 721), (W, 721), (26, 34, 44, 255), 3)
    for x0 in (250,):
        cv2.rectangle(land, (x0, 721), (470, 740), (10, 8, 8, 255), -1)
    mat = np.array([(600, 880), (1360, 880), (1460, 1010), (500, 1010)], np.int32)   # reed mat (chatai)
    cv2.fillPoly(land, [mat], (70, 118, 150, 255), cv2.LINE_AA)
    for k in range(1, 18):
        u = k / 18.0
        cv2.line(land, (int(600 + 760 * u - 100 * u + 100 * u), 880), (int(500 + 960 * u), 1010), (56, 96, 124, 255), 2, cv2.LINE_AA)
    for yy in range(890, 1010, 14):
        cv2.line(land, (int(600 - (yy - 880) * 100 / 130), yy), (int(1360 + (yy - 880) * 100 / 130), yy), (60, 102, 132, 255), 1)
    cv2.ellipse(land, (1720, 905), (52, 58), 0, 0, 360, (40, 72, 120, 255), -1, cv2.LINE_AA)      # an earthen pot
    cv2.ellipse(land, (1720, 850), (26, 10), 0, 0, 360, (30, 56, 96, 255), -1, cv2.LINE_AA)
    env.land = land
    env.loc_state.update({"window": (wx0, wy0, wx1, wy1), "door": (dx0, dy0, dx1, dy1), "lamp": (960, 528)})


def _station(env, rng):
    land = env.land
    cv2.rectangle(land, (0, 600), (W, 735), (50, 56, 62, 255), -1)              # ballast
    land[600:735, :, :3] = np.clip(land[600:735, :, :3].astype("float32") + _noise(rng, 135, W, 6.0), 0, 255).astype(np.uint8)
    for x in range(-10, W, 38):                                                   # sleepers
        cv2.rectangle(land, (x, 640), (x + 16, 712), (34, 46, 58, 255), -1)
    for yy in (652, 700):                                                         # rails
        cv2.line(land, (0, yy), (W, yy), (120, 126, 134, 255), 5, cv2.LINE_AA)
        cv2.line(land, (0, yy + 4), (W, yy + 4), (60, 64, 70, 255), 2)
    cv2.rectangle(land, (0, 735), (W, 790), (62, 66, 72, 255), -1)              # platform edge face
    top = np.full((H - 790, W, 3), (82, 86, 90), "float32") + _noise(rng, H - 790, W, 3.0)
    land[790:, :, :3] = np.clip(top, 0, 255).astype(np.uint8)
    land[735:, :, 3] = 255
    cv2.rectangle(land, (0, 792), (W, 806), (40, 150, 190, 255), -1)            # the yellow line
    for yy in range(840, H, 70):
        cv2.line(land, (0, yy), (W, yy), (70, 74, 78, 255), 1)
    for x in range(0, W, 120):
        cv2.line(land, (x, 806), (x, H), (70, 74, 78, 255), 1)
    cv2.fillPoly(land, [np.array([(0, 70), (1340, 70), (1340, 132), (0, 160)], np.int32)], (34, 38, 44, 255), cv2.LINE_AA)
    for x in range(0, 1340, 26):
        cv2.line(land, (x, 72), (x, 140), (44, 48, 54, 255), 2)
    for x in (180, 600, 1020):                                                    # pillars
        cv2.rectangle(land, (x, 140), (x + 28, 795), (66, 70, 78, 255), -1)
        cv2.rectangle(land, (x + 3, 140), (x + 8, 795), (86, 90, 98, 255), -1)
    cv2.rectangle(land, (400, 180), (720, 246), (24, 26, 30, 255), -1)           # a hanging board (no readable text)
    cv2.rectangle(land, (408, 188), (712, 238), (40, 150, 190, 255), -1)
    for x in (440, 690):
        cv2.line(land, (x, 140), (x, 180), (30, 30, 34, 255), 2)
    cv2.rectangle(land, (1380, 860), (1560, 878), (38, 54, 70, 255), -1)          # a bench
    cv2.rectangle(land, (1380, 820), (1560, 834), (38, 54, 70, 255), -1)
    for x in (1392, 1540):
        cv2.rectangle(land, (x, 860), (x + 10, 930), (30, 34, 40, 255), -1)
    env.loc_state.update({"bulb": (840, 250), "signal": (1700, 470)})


def _cremation(env, rng):
    far = env.far
    t = np.array([(1560, HORIZON + 30), (1560, 470), (1585, 420), (1600, 360), (1615, 420), (1640, 470), (1640, HORIZON + 30)], np.int32)
    cv2.fillPoly(far, [t], (30, 30, 34, 255), cv2.LINE_AA)                       # a small temple far away
    cv2.line(far, (1600, 360), (1600, 330), (30, 30, 34, 255), 3)
    land = env.land
    for _ in range(26):                                                           # ash patches
        x, y = int(rng.uniform(0, W)), int(rng.uniform(760, H))
        cv2.ellipse(land, (x, y), (int(rng.uniform(40, 140)), int(rng.uniform(10, 30))), 0, 0, 360, (56, 60, 64, 255), -1, cv2.LINE_AA)
    for k, yy in enumerate((724, 748, 772)):                                     # ghat steps down to the river
        cv2.rectangle(land, (60 - k * 20, yy), (560 + k * 30, yy + 22), (70 - k * 4, 72 - k * 4, 76 - k * 4, 255), -1)
    for _ in range(14):                                                           # broken pots
        x, y = int(rng.uniform(500, 1850)), int(rng.uniform(800, 1040))
        r = int(rng.uniform(10, 22))
        cv2.ellipse(land, (x, y), (r, int(r * 0.8)), 0, 200 if rng.uniform() < 0.5 else 0, 360, (28, 48, 78, 255), -1, cv2.LINE_AA)
    env.loc_state.update({"pyre": (1360, 880)})


def _rajbari(env, rng):
    far = env.far
    wall_c = (58, 60, 66, 255)
    cv2.rectangle(far, (380, 250), (1540, HORIZON + 40), wall_c, -1)
    cv2.rectangle(far, (180, 360), (380, HORIZON + 40), (52, 54, 60, 255), -1)   # side wings
    cv2.rectangle(far, (1540, 360), (1740, HORIZON + 40), (52, 54, 60, 255), -1)
    blot = cv2.resize(rng.uniform(-1, 1, (30, 60)).astype("float32"), (W, H))
    m = far[..., 3] > 0
    far[..., :3][m] = np.clip(far[..., :3][m].astype("float32") + (blot[m] * 10)[:, None], 0, 255).astype(np.uint8)
    x = 380
    pts = [(380, 250)]
    while x < 1540:                                                               # broken parapet
        x += int(rng.uniform(20, 60))
        pts.append((min(x, 1540), 250 - int(rng.uniform(0, 26)) * (1 if rng.uniform() < 0.7 else 0)))
    pts += [(1540, 250)]
    cv2.fillPoly(far, [np.array(pts + [(1540, 262), (380, 262)], np.int32)], wall_c, cv2.LINE_AA)
    wins = []
    for row, (y0, y1) in enumerate(((300, 385), (430, 515))):
        for k in range(12):
            x0 = 420 + k * 92
            if 830 < x0 < 1080 and row == 1:
                continue
            cv2.rectangle(far, (x0, y0 + 20), (x0 + 44, y1), (16, 16, 20, 255), -1)
            cv2.ellipse(far, (x0 + 22, y0 + 20), (22, 20), 0, 180, 360, (16, 16, 20, 255), -1, cv2.LINE_AA)
            wins.append((x0 + 22, (y0 + y1) // 2 + 8))
    for k in range(4):                                                            # side-wing windows
        for xx in (230 + k * 0, 1600):
            cv2.rectangle(far, (xx + k * 0, 400 + k * 36), (xx + 40, 420 + k * 36), (16, 16, 20, 255), -1) if k < 2 else None
    cv2.fillPoly(far, [np.array([(820, 410), (1100, 410), (960, 330)], np.int32)], (70, 72, 78, 255), cv2.LINE_AA)  # pediment
    for x in range(840, 1100, 62):                                                # columns
        cv2.rectangle(far, (x, 410), (x + 22, HORIZON + 30), (118, 122, 128, 255), -1)
        cv2.rectangle(far, (x + 3, 410), (x + 7, HORIZON + 30), (140, 144, 150, 255), -1)
    for k in range(4):                                                            # steps
        cv2.rectangle(far, (780 - k * 30, HORIZON + 30 + k * 12), (1140 + k * 30, HORIZON + 42 + k * 12),
                      (80 - k * 3, 82 - k * 3, 86 - k * 3, 255), -1)
    for _ in range(22):                                                           # creepers hanging on the walls
        x, y = int(rng.uniform(380, 1540)), int(rng.uniform(255, 300))
        ln = int(rng.uniform(40, 200))
        for k in range(0, ln, 9):
            cv2.circle(far, (x + int(6 * math.sin(k * 0.2)), y + k), int(rng.uniform(4, 9)), (20, 34, 24, 255), -1, cv2.LINE_AA)
    land = env.land
    for k in range(1, 12):                                                        # stone courtyard in perspective
        u = (k / 12.0) ** 1.6
        yy = int(HORIZON + 60 + (H - HORIZON - 60) * u)
        cv2.line(land, (0, yy), (W, yy), (36, 44, 42, 255), 1)
    for k in range(-10, 11):
        cv2.line(land, (960 + k * 40, HORIZON + 60), (960 + k * 260, H), (36, 44, 42, 255), 1, cv2.LINE_AA)
    env.loc_state.update({"windows": wins, "lit": wins[7] if len(wins) > 7 else (960, 340)})


# ====================================================================== per frame (things that move by themselves)
def flicker(t, seed=0.0, dead=False):
    f = 0.9 + 0.06 * math.sin(t * 21 + seed) * math.sin(t * 6.7 + seed) + 0.04 * math.sin(t * 37 + seed)
    if dead and (t * 1.7 + seed) % 9.0 < 0.25:                                    # a failing bulb dies for a moment
        f *= 0.15
    return f


def draw(env, pt, t, wind, state):
    """back-layer vector drawing for the place (behind the characters); returns light points"""
    loc = env.loc
    ls = env.loc_state
    lights = []
    if loc == "road":
        x, y, h = ls["lamp"]
        fl = flicker(t, 1.3, dead=True)
        pt.line((x, y), (x, y - h), (30, 34, 40), 12)
        pt.line((x, y - h), (x - 90, y - h - 10), (30, 34, 40), 7)
        pt.ellipse((x - 96, y - h), 26, 10, 0, (40, 44, 52))
        pt.ellipse((x - 96, y - h + 8), 16, 6, 0, (int(80 + 120 * fl), int(170 + 70 * fl), int(220 + 30 * fl)))
        lights.append((x - 96, y - h + 30, 640, (40, 130, 210), 0.55 * fl))
    elif loc == "jungle":                                                         # moonlight falling through the canopy
        lights.append((1000, 860, 1000, (70, 62, 52), 0.55 + 0.05 * math.sin(t * 0.4)))
    elif loc == "house_interior":
        wx0, wy0, wx1, wy1 = ls["window"]
        rain = env.spec.get("outside_rain", 0.0)
        flash = _flash(env, t)
        if flash:
            pt.poly([(wx0, wy0), (wx1, wy0), (wx1, wy1), (wx0, wy1)], (200 * flash + 40, 190 * flash + 22, 180 * flash + 14))
        if rain:
            rng = np.random.default_rng(int(t * 30))
            for _ in range(int(40 * rain)):
                x, y = rng.uniform(wx0, wx1), rng.uniform(wy0, wy1 - 20)
                pt.line((x, y), (x - 3, y + 20), (120, 118, 112), 1.2)
        for x in range(wx0 + 30, wx1, 46):                                        # window bars
            pt.line((x, wy0), (x, wy1), (40, 52, 64), 8)
        dx0, dy0, dx1, dy1 = ls["door"]
        op, shake = state.get("door_open", 0.0), state.get("door_shake", 0.0)
        if op > 0.02:                                                             # outside, through the open door
            pt.poly([(dx0, dy0), (dx1, dy0), (dx1, dy1), (dx0, dy1)], (38 + 150 * flash, 22 + 140 * flash, 14 + 130 * flash))
            if rain:
                rng = np.random.default_rng(int(t * 30) + 5)
                for _ in range(int(60 * rain * op)):
                    x, y = rng.uniform(dx0, dx1), rng.uniform(dy0, dy1 - 24)
                    pt.line((x, y), (x - 4, y + 24), (110, 110, 104), 1.2)
        wd = (dx1 - dx0) * (1 - 0.86 * op)                                         # the door panel swings inward
        sx = shake * math.sin(t * 55)
        skew = 46 * op
        panel = [(dx0 + sx, dy0), (dx0 + wd + sx, dy0 - skew), (dx0 + wd + sx, dy1 + skew * 0.3), (dx0 + sx, dy1)]
        pt.poly(panel, (40, 58, 80) if op < 0.5 else (48, 68, 92))
        for k in range(1, 5):
            xx = dx0 + wd * k / 5 + sx
            pt.line((xx, dy0 - skew * k / 5), (xx, dy1 + skew * 0.3 * k / 5), (30, 44, 62), 3)
        for yy in (dy0 + 120, dy1 - 140):
            pt.line((dx0 + sx, yy), (dx0 + wd + sx, yy - skew * 0.4), (30, 44, 62), 6)
        pt.circle((dx0 + wd * 0.86 + sx, (dy0 + dy1) / 2), 7, (60, 120, 150))     # the chain-latch ring
        lx, ly = ls["lamp"]                                                       # the oil lamp (pradip) in the niche
        fl = flicker(t, 0.7)
        pt.ellipse((lx, ly), 24, 9, 0, (40, 70, 120))
        pt.ellipse((lx + 16, ly - 4), 6, 4, 0, (40, 70, 120))
        fh = 16 * fl + 2 * math.sin(t * 29)
        pt.ellipse((lx + 18 + math.sin(t * 8) * 1.5, ly - 12 - fh * 0.4), 5, fh, 0, (90, 200, 255))
        pt.ellipse((lx + 18, ly - 10 - fh * 0.3), 2.4, fh * 0.45, 0, (220, 250, 255))
        lights.append((lx + 18, ly - 20, 900, (36, 100, 170), 0.62 * fl))
    elif loc == "railway_station":
        bx, by = ls["bulb"]
        fl = flicker(t, 2.1, dead=True)
        pt.line((bx, 132), (bx, by - 20), (24, 24, 28), 2)
        pt.ellipse((bx, by - 18), 34, 12, 0, (34, 38, 44))
        pt.circle((bx, by - 4), 11, (int(120 + 120 * fl), int(200 + 50 * fl), int(220 + 30 * fl)))
        lights.append((bx, by + 10, 700, (60, 150, 200), 0.6 * fl))
        sx, sy = ls["signal"]
        pt.line((sx, sy + 90), (sx, sy - 40), (30, 30, 34), 6)
        pt.ellipse((sx, sy - 40), 14, 26, 0, (24, 24, 28))
        on = (t % 2.0) < 1.2
        pt.circle((sx, sy - 48), 7, (40, 40, 230) if on else (30, 30, 70))
        if on:
            lights.append((sx, sy - 48, 120, (20, 20, 200), 0.5))
        for k in range(5):                                                        # moths round the bulb
            a = t * (2.3 + k * 0.4) + k
            pt.circle((bx + 46 * math.cos(a) + 10 * math.sin(a * 3), by + 22 * math.sin(a * 1.3)), 2.2, (150, 170, 180))
    elif loc == "cremation_ground":
        x, y = ls["pyre"]
        for k in range(4):                                                        # stacked logs
            for j in range(3 - (k > 1)):
                pt.ellipse((x - 70 + j * 70 + (k % 2) * 35, y - 14 - k * 22), 46, 12, 0, (30, 46, 62))
        rng = np.random.default_rng(int(t * 18))
        for k in range(10):                                                       # flames, every tongue on its own
            ph = k * 1.7
            hgt = 70 + 55 * (0.5 + 0.5 * math.sin(t * 7 + ph)) + rng.uniform(0, 14)
            fx = x - 90 + k * 20 + 6 * math.sin(t * 5 + ph) + wind * 8
            base = y - 90
            pt.ellipse((fx + wind * 10, base - hgt * 0.45), 16, hgt * 0.55, 6 * math.sin(t * 3 + ph) + wind * 6, (20, 80, 220))
            pt.ellipse((fx + wind * 8, base - hgt * 0.36), 10, hgt * 0.4, 6 * math.sin(t * 3 + ph), (50, 170, 255))
            pt.ellipse((fx + wind * 6, base - hgt * 0.25), 5, hgt * 0.24, 0, (170, 235, 255))
        for k in range(16):                                                       # sparks rising
            age = (t * 0.8 + k * 0.137) % 1.0
            sx = x - 60 + (k * 37) % 120 + 40 * age * math.sin(k + t) + 60 * wind * age
            sy = y - 140 - 380 * age
            if age < 0.85:
                pt.circle((sx, sy), 2.4 * (1 - age), (60, 180, 255))
        lights.append((x, y - 150, 820, (30, 110, 230), 0.7 * flicker(t, 0.3)))
    elif loc == "rajbari":
        for k in range(5):                                                        # bats
            ph = (t * 0.09 + k * 0.21) % 1.0
            bx, by = -100 + (W + 200) * ph, 180 + 60 * k + 30 * math.sin(t * 2 + k)
            f = 10 * math.sin(t * 18 + k)
            pt.line((bx - 14, by - f), (bx, by), (16, 16, 20), 3)
            pt.line((bx, by), (bx + 14, by - f), (16, 16, 20), 3)
    return lights


def _flash(env, t):
    for lt in env.lightning:
        d = t - lt
        if 0 <= d < 0.08 or 0.16 <= d < 0.22:
            return 1.0
    return 0.0


def atmosphere(env, frame, cam, t, wind):
    """screen-space effects of the place: pyre smoke, the lit palace window (on the far layer)"""
    loc = env.loc
    ls = env.loc_state
    Hh, Ww = frame.shape[:2]
    if loc == "cremation_ground":
        x, y = ls["pyre"]
        for k in range(9):                                                        # soft smoke puffs rising and drifting
            age = (t * 0.07 + k / 9.0) % 1.0
            px = x + (40 + 260 * wind) * age + 30 * math.sin(t * 0.6 + k)
            py = y - 170 - 600 * age
            r = (40 + 160 * age) * cam.s
            sx, sy = cam.to_screen(px, py)
            x0, y0, x1, y1 = int(max(0, sx - r)), int(max(0, sy - r)), int(min(Ww, sx + r)), int(min(Hh, sy + r))
            if x1 > x0 and y1 > y0:
                yy, xx = np.mgrid[y0:y1, x0:x1].astype("float32")
                g = np.clip(1 - np.sqrt((xx - sx) ** 2 + (yy - sy) ** 2) / r, 0, 1) ** 1.5 * 0.32 * (1 - age)
                frame[y0:y1, x0:x1] = frame[y0:y1, x0:x1] * (1 - g[..., None]) + np.array([96, 98, 100], "float32") * g[..., None]
    elif loc == "rajbari":
        lx, ly = ls["lit"]
        M = cam.matrix(0.5)
        sx, sy = M[0, 0] * lx + M[0, 1] * ly + M[0, 2], M[1, 0] * lx + M[1, 1] * ly + M[1, 2]
        fl = flicker(t, 4.0, dead=True)
        r = 40 * M[0, 0]
        x0, y0, x1, y1 = int(max(0, sx - r * 2)), int(max(0, sy - r * 2)), int(min(Ww, sx + r * 2)), int(min(Hh, sy + r * 2))
        if x1 > x0 and y1 > y0:
            yy, xx = np.mgrid[y0:y1, x0:x1].astype("float32")
            g = np.clip(1 - np.sqrt(((xx - sx) / 0.6) ** 2 + (yy - sy) ** 2) / (r * 2), 0, 1) ** 2 * fl
            frame[y0:y1, x0:x1] += g[..., None] * np.array([40, 140, 220], "float32")
    return frame
