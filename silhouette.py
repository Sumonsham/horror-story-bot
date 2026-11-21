"""Procedural, fully rigged SILHOUETTE characters (shadow-puppet style) - the zero-cost fallback of the character
pipeline. Nothing is downloaded, no image service is called: every character is drawn by code from its Visual Bible
(age, gender, build, clothes, hair, ghost or human), so it is always available, always the same, and - unlike a
flat picture - it has real joints: head, torso, upper/lower arms, upper/lower legs. That lets the compositor make it
breathe, nod, turn its head, raise a hand, point, tremble and walk.

It has no face (a silhouette), so there is no lip-sync for it - the compositor shows speech with head and hand
movement instead and never draws a fake mouth.
"""
import hashlib
import math

from PIL import Image, ImageDraw, ImageFilter


def _rng(seed_text):
    h = int(hashlib.sha1(str(seed_text).encode()).hexdigest()[:8], 16)
    return lambda a, b, k=0: a + (b - a) * (((h >> (k % 24)) & 0xFF) / 255.0)


def build(bible):
    """Visual Bible -> rig parameters (stable: the same bible always gives the same figure)."""
    look = f"{bible.get('look', '')} {bible.get('name', '')}".lower()
    r = _rng(bible.get("id") or bible.get("name"))
    age = str(bible.get("age", "adult")).lower()
    female = str(bible.get("gender", "")).lower().startswith("f")
    kind = str(bible.get("kind", "human")).lower()
    child = any(w in age for w in ("child", "boy", "girl", "kid")) or any(w in look for w in ("child", "little boy", "little girl"))
    old = "old" in age or any(w in look for w in ("old", "elderly", "grey hair", "white beard", "aged"))
    height = 0.62 if child else (0.94 if old else r(0.98, 1.04, 1))
    width = r(0.92, 1.12, 3) * (0.9 if female else 1.0) * (1.15 if any(w in look for w in ("fat", "heavy", "stout")) else 1.0)
    return {
        "female": female, "child": child, "old": old, "ghost": kind.startswith("ghost") or "ghost" in look,
        "height": height, "width": width, "stoop": 9.0 if old else 0.0,
        "sari": female and not child and not any(w in look for w in ("jeans", "shirt", "salwar")),
        "dhoti": (not female) and any(w in look for w in ("dhoti", "priest", "tantrik", "sadhu", "village")),
        "shawl": any(w in look for w in ("shawl", "chador", "wrap", "blanket")),
        "bun": female and (old or "bun" in look),
        "long_hair": female and not old,
        "beard": (not female) and (old or "beard" in look),
        "matted": any(w in look for w in ("tantrik", "sadhu", "matted", "jata")),
        "stick": old and not female or "stick" in look or "lathi" in look,
        "lantern": "lantern" in look or "hurricane" in look,
    }


POSES = {
    # degrees from straight down; POSITIVE = away from the body (outwards / up), 180 = straight up;
    # a negative forearm angle points back across the body (hands to the face)
    "neutral": dict(head=0, torso=0, ua_l=8, la_l=4, ua_r=8, la_r=4, ul_l=3, ll_l=0, ul_r=3, ll_r=0),
    "talking": dict(head=4, torso=1, ua_l=8, la_l=4, ua_r=35, la_r=70, ul_l=3, ll_l=0, ul_r=3, ll_r=0),
    "fear": dict(head=-8, torso=-6, ua_l=40, la_l=-150, ua_r=40, la_r=-150, ul_l=6, ll_l=-4, ul_r=6, ll_r=-4),
    "shock": dict(head=-14, torso=-9, ua_l=150, la_l=170, ua_r=150, la_r=170, ul_l=10, ll_l=0, ul_r=10, ll_r=0),
    "point": dict(head=6, torso=3, ua_l=8, la_l=4, ua_r=95, la_r=90, ul_l=3, ll_l=0, ul_r=3, ll_r=0),
    "sad": dict(head=18, torso=6, ua_l=4, la_l=2, ua_r=4, la_r=2, ul_l=2, ll_l=0, ul_r=2, ll_r=0),
}


def blend(a, b, t):
    return {k: a[k] + (b[k] - a[k]) * t for k in a}


def render(rig, pose, h_px=600, breath=0.0, walk=0.0, ghost_alpha=0.72):
    """One frame of the character: RGBA image (feet at the bottom centre). pose = dict of joint angles."""
    s = h_px / 600.0 * rig["height"]
    wscale = rig["width"]
    W_, H_ = int(420 * s * max(1.0, wscale)) + 40, int(640 * s) + 40
    im = Image.new("RGBA", (W_, H_), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    ink = (236, 240, 245, int(255 * ghost_alpha)) if rig["ghost"] else (12, 11, 14, 255)
    cx, ground = W_ / 2, H_ - 14
    hip_y = ground - 285 * s
    sw = 1.0 + 0.012 * breath
    p = dict(pose)
    if walk:
        ph = math.sin(walk)
        p.update(ul_l=p["ul_l"] + 14 * ph, ul_r=p["ul_r"] - 14 * ph, ll_l=p["ll_l"] - 8 * max(0, ph),
                 ll_r=p["ll_r"] - 8 * max(0, -ph), ua_l=p["ua_l"] + 12 * ph, ua_r=p["ua_r"] - 12 * ph)
        hip_y -= 5 * s * abs(math.sin(walk))

    def seg(x, y, ang, length, width):
        a = math.radians(ang)
        x2, y2 = x + math.sin(a) * length, y + math.cos(a) * length
        d.line([(x, y), (x2, y2)], fill=ink, width=max(2, int(width)))
        r_ = width / 2
        d.ellipse([x2 - r_, y2 - r_, x2 + r_, y2 + r_], fill=ink)
        return x2, y2

    # legs (under the clothes)
    for side, ul, ll in ((-1, "ul_l", "ll_l"), (1, "ul_r", "ll_r")):
        hx = cx + side * 26 * s * wscale
        kx, ky = seg(hx, hip_y, side * p[ul], 140 * s, 34 * s * wscale)
        fx, fy = seg(kx, ky, side * (p[ul] + p[ll]), 140 * s, 28 * s * wscale)
        d.ellipse([fx - 22 * s, fy - 8 * s, fx + 22 * s, fy + 8 * s], fill=ink)
    # torso (leans with the stoop and the pose)
    lean = rig["stoop"] + p["torso"]
    a = math.radians(-lean)
    neck_x = cx + math.sin(a) * -230 * s
    neck_y = hip_y - math.cos(a) * 230 * s * sw
    tw = 62 * s * wscale * sw
    mid_x, mid_y = (cx + neck_x) / 2, (hip_y + neck_y) / 2
    d.polygon([(cx - tw * 0.8, hip_y + 6 * s), (cx + tw * 0.8, hip_y + 6 * s), (mid_x + tw * 0.68, mid_y),
               (neck_x + tw * 0.95, neck_y + 30 * s), (neck_x + tw * 0.6, neck_y + 14 * s),
               (neck_x - tw * 0.6, neck_y + 14 * s), (neck_x - tw * 0.95, neck_y + 30 * s),
               (mid_x - tw * 0.68, mid_y)], fill=ink)
    for side in (-1, 1):                               # rounded shoulders
        sx_ = neck_x + side * tw * 0.78
        d.ellipse([sx_ - 20 * s, neck_y + 12 * s, sx_ + 20 * s, neck_y + 50 * s], fill=ink)
    # clothes
    if rig["sari"]:
        d.polygon([(cx - tw * 1.05, hip_y - 20 * s), (cx + tw * 1.05, hip_y - 20 * s), (cx + tw * 1.55, ground - 4),
                   (cx - tw * 1.55, ground - 4)], fill=ink)
        d.polygon([(neck_x + tw * 0.7, neck_y + 20 * s), (neck_x + tw * 1.15, neck_y + 40 * s),
                   (cx + tw * 1.6, hip_y + 120 * s), (cx + tw * 1.2, hip_y + 130 * s)], fill=ink)     # the pallu
    elif rig["dhoti"]:
        d.polygon([(cx - tw, hip_y - 10 * s), (cx + tw, hip_y - 10 * s), (cx + tw * 1.2, ground - 90 * s),
                   (cx - tw * 1.2, ground - 90 * s)], fill=ink)
    if rig["shawl"]:
        d.polygon([(neck_x - tw * 1.2, neck_y + 18 * s), (neck_x + tw * 1.2, neck_y + 18 * s),
                   (cx + tw * 1.3, hip_y - 30 * s), (cx - tw * 1.3, hip_y - 30 * s)], fill=ink)
    # arms
    hands = []
    for side, ua, la in ((-1, "ua_l", "la_l"), (1, "ua_r", "la_r")):
        sx = neck_x + side * tw * 0.9
        ex, ey = seg(sx, neck_y + 26 * s, side * p[ua], 112 * s, 22 * s * wscale)
        hx, hy = seg(ex, ey, side * p[la], 104 * s, 18 * s * wscale)
        d.ellipse([hx - 13 * s, hy - 13 * s, hx + 13 * s, hy + 13 * s], fill=ink)
        hands.append((hx, hy))
    if rig["stick"]:
        hx, hy = hands[1]
        d.line([(hx, hy - 30 * s), (hx + 10 * s, ground)], fill=ink, width=max(2, int(7 * s)))
    if rig["lantern"]:
        hx, hy = hands[0]
        d.line([(hx, hy), (hx, hy + 26 * s)], fill=ink, width=max(1, int(3 * s)))
        d.ellipse([hx - 30 * s, hy + 14 * s, hx + 30 * s, hy + 74 * s], fill=(255, 170, 70, 70))      # the glow
        d.polygon([(hx - 12 * s, hy + 26 * s), (hx + 12 * s, hy + 26 * s), (hx + 15 * s, hy + 62 * s),
                   (hx - 15 * s, hy + 62 * s)], fill=(255, 205, 120, 255))
        d.rectangle([hx - 16 * s, hy + 60 * s, hx + 16 * s, hy + 66 * s], fill=ink)
    # head
    ha = math.radians(-(lean * 0.6 + p["head"]))
    hcx = neck_x + math.sin(ha) * -46 * s
    hcy = neck_y - math.cos(ha) * 46 * s
    hr = 44 * s * (1.12 if rig["child"] else 1.0)
    d.ellipse([hcx - hr * 0.86, hcy - hr, hcx + hr * 0.86, hcy + hr], fill=ink)
    d.polygon([(neck_x - 14 * s, neck_y + 24 * s), (neck_x + 14 * s, neck_y + 24 * s), (hcx + 12 * s, hcy + hr * 0.6),
               (hcx - 12 * s, hcy + hr * 0.6)], fill=ink)
    face_dir = 1 if p["head"] >= 0 else -1
    d.polygon([(hcx + face_dir * hr * 0.8, hcy - 4 * s), (hcx + face_dir * hr * 1.02, hcy + 8 * s),
               (hcx + face_dir * hr * 0.8, hcy + 14 * s)], fill=ink)                                  # the nose
    if rig["bun"]:
        d.ellipse([hcx - face_dir * hr * 0.95 - 20 * s, hcy - hr * 0.6, hcx - face_dir * hr * 0.95 + 20 * s,
                   hcy - hr * 0.6 + 40 * s], fill=ink)
    if rig["long_hair"]:
        d.polygon([(hcx - hr * 0.9, hcy - hr * 0.3), (hcx + hr * 0.9, hcy - hr * 0.3), (hcx + hr * 0.7, hcy + hr * 2.4),
                   (hcx - hr * 0.9, hcy + hr * 2.6)], fill=ink)
    if rig["matted"]:
        d.ellipse([hcx - hr * 0.7, hcy - hr * 1.7, hcx + hr * 0.7, hcy - hr * 0.6], fill=ink)
    if rig["beard"]:
        d.polygon([(hcx - hr * 0.5, hcy + hr * 0.3), (hcx + hr * 0.6, hcy + hr * 0.3),
                   (hcx + face_dir * hr * 0.2, hcy + hr * 1.6)], fill=ink)
    if rig["ghost"]:                                  # two pale glowing eyes - the only "face" a silhouette gets
        for k in (-0.28, 0.2):
            ex = hcx + face_dir * hr * 0.35 + k * hr
            d.ellipse([ex - 5 * s, hcy - 6 * s, ex + 5 * s, hcy + 2 * s], fill=(190, 255, 220, 255))
        im = im.filter(ImageFilter.GaussianBlur(1.2 * s))
    return im


def pose_for(expression, t, talking=0.0, rig=None):
    """the pose for an expression at time t (seconds), with small living movement; talking 0..1 = voice loudness"""
    base = dict(POSES.get(expression, POSES["neutral"]))
    base["head"] += 2.5 * math.sin(t * 0.9) + 6.0 * talking * math.sin(t * 7.0)       # nods while speaking
    base["ua_r"] += 10.0 * talking * (0.5 + 0.5 * math.sin(t * 3.1))                     # the hand moves with the words
    base["la_r"] += 18.0 * talking * (0.5 + 0.5 * math.sin(t * 3.7))
    if expression in ("fear", "shock"):
        base["torso"] += 1.6 * math.sin(t * 31)                                            # trembling
        base["head"] += 2.0 * math.sin(t * 27)
    return base
