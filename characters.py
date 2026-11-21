"""AUTOMATIC CHARACTER CREATOR + ASSET LIBRARY (+ background library) - zero cost.

* Character ID: stable per character. Series characters keep one ID for ever (taranath, bapi, nilkantha...);
  a one-story character gets <name>-<story date>. The same ID is never made twice - it is taken from the library.
* Visual Bible: age, gender, build, clothes, hair, kind (human / ghost) from the story's character list.
* Assets ("photo" mode, free Cloudflare picture model - the same one the bot already uses):
    reference  - full body, plain grey studio background (the identity every other picture copies)
    neutral / talking / fear / shock (+ blink, sad, angry, happy ONLY when a scene needs them)
  each turned into a transparent PNG (the plain studio background is keyed out locally - no extra tool),
  with its face box (OpenCV) for the mouth/eye swap. Quality check: a face must be found where the reference
  has it; a failed picture is retried twice and otherwise left out (the neutral one is used) - never faked.
* "silhouette" mode: when no picture can be made (no key, free limit used, the safety filter said no) the
  character is drawn by code (silhouette.py) - always available, fully rigged, but no face / no lip-sync.
* Storage: assets/characters/index.json (ID, version, bible, files, provider, quality, dates) in the repo;
  the pictures themselves in the GitHub Release "characters" (no weight on the repo), downloaded when needed.
Nothing here costs money: the picture function given to the library is the bot's own free Cloudflare call,
and zerocost.py still guards every request.
"""
import datetime as dt
import hashlib
import json
import os
import re

import numpy as np
from PIL import Image, ImageFilter

import silhouette

BASE_SET = ("neutral", "talking", "fear", "shock")
EXTRA_SET = ("blink", "sad", "angry", "happy")
EXPR_TEXT = {
    "neutral": "calm neutral face, mouth closed, eyes open looking slightly to the side",
    "talking": "speaking, mouth clearly open as if saying 'aa', eyes open, same head angle",
    "blink": "eyes fully closed, mouth closed, calm, same head angle",
    "fear": "terrified expression, eyes wide open, eyebrows raised, mouth slightly open",
    "shock": "shocked screaming expression, mouth wide open, eyes very wide",
    "sad": "sad expression, eyes lowered, mouth closed",
    "angry": "angry expression, eyebrows down, jaw tight",
    "happy": "gentle smile, eyes soft",
}
STUDIO = ("plain flat light-grey studio background, even soft frontal light, full body visible from head to feet, "
          "standing, three-quarter view, arms relaxed at the sides, nothing else in the picture")


def slug(s):
    s = re.sub(r"[^a-z0-9]+", "-", str(s or "").lower()).strip("-")
    return s[:40] or "x"


def char_id(c, series=None, story_key=""):
    """stable ID: series characters for ever, others per story"""
    base = slug(c.get("id") or c.get("name"))
    return base if series else f"{base}-{slug(story_key)}" if story_key else base


def bible(c, cid):
    look = str(c.get("look", "")).strip()
    return {"id": cid, "name": c.get("name", cid), "gender": c.get("gender", ""), "age": c.get("age", "adult"),
            "kind": c.get("kind", "human"), "look": look,
            "prompt": (f"ONE {'ghostly pale ' if str(c.get('kind', '')).startswith('ghost') else ''}"
                       f"{c.get('age', 'adult')} {'woman' if str(c.get('gender', '')).startswith('f') else 'man'} "
                       f"from Bengal, India: {look}. Realistic, cinematic, photorealistic film character.")}


# ------------------------------------------------------------------ local image helpers (no extra libraries)
def key_out(rgb, tol=38.0):
    """plain studio background -> transparent: the colour of the border is the background"""
    a = np.asarray(rgb.convert("RGB"), dtype=np.float32)
    border = np.concatenate([a[:6].reshape(-1, 3), a[-6:].reshape(-1, 3), a[:, :6].reshape(-1, 3), a[:, -6:].reshape(-1, 3)])
    bg = np.median(border, axis=0)
    dist = np.sqrt(((a - bg) ** 2).sum(axis=2))
    alpha = np.clip((dist - tol * 0.6) / (tol * 0.8), 0, 1)
    try:                                              # keep only the big connected figure (no specks)
        import cv2
        m = (alpha > 0.5).astype(np.uint8)
        n, lab, stats, _ = cv2.connectedComponentsWithStats(m, 8)
        if n > 1:
            big = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
            keep = cv2.dilate((lab == big).astype(np.uint8), np.ones((9, 9), np.uint8))
            alpha *= keep
        alpha = cv2.GaussianBlur(alpha, (0, 0), 1.2)
    except Exception:
        pass
    out = np.dstack([a, alpha * 255]).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def face_box(rgba):
    try:
        import animate
        f = animate.find_faces(np.asarray(rgba.convert("RGB")))
        return list(max(f, key=lambda x: x["box"][2])["box"]) if f else None
    except Exception:
        return None


def _hist_sim(a, b):
    try:
        ha = np.histogram(np.asarray(a.convert("L")), bins=32, range=(0, 255))[0].astype(float)
        hb = np.histogram(np.asarray(b.convert("L")), bins=32, range=(0, 255))[0].astype(float)
        ha /= ha.sum() + 1e-9
        hb /= hb.sum() + 1e-9
        return float(np.minimum(ha, hb).sum())
    except Exception:
        return 0.0


class Library:
    """image_fn(prompt, ref_path, seed, w, h) -> jpeg/png bytes, or raise. upload_fn(path, name) -> url or ''.
    Without image_fn (no free key / limit used) every new character is a silhouette."""

    def __init__(self, assets_dir, cache_dir, image_fn=None, upload_fn=None, log=print, style=""):
        self.dir = os.path.join(assets_dir, "characters")
        self.cache = cache_dir
        os.makedirs(self.cache, exist_ok=True)
        self.index_path = os.path.join(self.dir, "index.json")
        try:
            with open(self.index_path, encoding="utf-8") as f:
                self.index = json.load(f)
        except Exception:
            self.index = {"chars": {}, "backgrounds": {}}
        self.index.setdefault("chars", {})
        self.index.setdefault("backgrounds", {})
        self.image_fn, self.upload_fn, self.log, self.style = image_fn, upload_fn, log, style
        self.stats = {"images_made": 0, "image_fail": 0, "cache_hits": 0, "silhouettes": 0, "bg_made": 0,
                      "bg_hits": 0}

    # -------------------------------------------------------------- storage
    def save(self):
        os.makedirs(self.dir, exist_ok=True)
        with open(self.index_path, "w", encoding="utf-8") as f:
            json.dump(self.index, f, ensure_ascii=False, indent=1)

    def _local(self, name):
        return os.path.join(self.cache, name)

    def _fetch(self, rec):
        """make sure the file of a record is on disk (download from the Release when needed)"""
        p = self._local(rec["file"])
        if os.path.exists(p):
            return p
        url = rec.get("url")
        if url:
            try:
                import requests
                r = requests.get(url, timeout=120)
                if r.ok and len(r.content) > 500:
                    with open(p, "wb") as f:
                        f.write(r.content)
                    return p
            except Exception as e:
                self.log("  character picture not downloaded:", str(e)[:100])
        return None

    def _store(self, img, name):
        p = self._local(name)
        img.save(p)
        url = ""
        if self.upload_fn:
            try:
                url = self.upload_fn(p, name) or ""
            except Exception as e:
                self.log("  character picture not uploaded (kept for this run):", str(e)[:100])
        return {"file": name, "url": url}

    # -------------------------------------------------------------- characters
    def get(self, cid):
        return self.index["chars"].get(cid)

    def ensure(self, c, cid, need=BASE_SET, seed=1):
        """the character's asset record, made only if it does not exist yet (new expressions are added)"""
        rec = self.index["chars"].get(cid)
        if rec is None:
            rec = {"id": cid, "version": 1, "bible": bible(c, cid), "mode": None, "expr": {},
                   "created": dt.date.today().isoformat(), "seed": seed}
            self.index["chars"][cid] = rec
        else:
            self.stats["cache_hits"] += 1
        rec["last_used"] = dt.date.today().isoformat()
        if rec.get("mode") == "silhouette" and self.image_fn and rec.get("retry_photo", True):
            rec["mode"] = None                         # (a silhouette from a day without pictures gets a photo later)
            rec["retry_photo"] = False
        if rec["mode"] != "silhouette":
            ok = self._ensure_photo(rec, need)
            if not ok:
                rec["mode"] = "silhouette"
        if rec["mode"] == "silhouette":
            self.stats["silhouettes"] += 1
            rec["rig"] = silhouette.build(rec["bible"])
        self.save()
        return rec

    def _ensure_photo(self, rec, need):
        if "reference" not in rec["expr"] or not self._fetch(rec["expr"]["reference"]):
            if not self.image_fn:
                return False
            img = self._make(rec, "reference", None)
            if img is None:
                return False
            fb = face_box(img)
            if not fb:
                self.log(f"  {rec['id']}: no face found on the reference picture - silhouette instead")
                return False
            rec["expr"]["reference"] = dict(self._store(img, f"{rec['id']}_v{rec['version']}_reference.png"), face=fb)
            rec["mode"] = "photo"
            rec["provider"] = "cloudflare"
        rec["mode"] = "photo"
        ref_p = self._fetch(rec["expr"]["reference"])
        for e in need:
            if e in rec["expr"] and self._fetch(rec["expr"][e]):
                continue
            if not self.image_fn:
                continue                                 # (later; the neutral face is used meanwhile)
            img = self._make(rec, e, ref_p)
            if img is None:
                continue
            fb = face_box(img)
            rfb = rec["expr"]["reference"].get("face")
            if not fb or (rfb and abs((fb[0] + fb[2] / 2) - (rfb[0] + rfb[2] / 2)) > 0.35 * rfb[2]):
                self.log(f"  {rec['id']}/{e}: face missing or moved - left out (not faked)")
                self.stats["image_fail"] += 1
                continue
            sim = _hist_sim(Image.open(ref_p), img)
            rec["expr"][e] = dict(self._store(img, f"{rec['id']}_v{rec['version']}_{e}.png"), face=fb,
                                  similarity=round(sim, 3))
        return True

    def _make(self, rec, expr, ref_path):
        b = rec["bible"]
        if expr == "reference":
            prompt = f"{self.style}. Character reference photo. {b['prompt']} {STUDIO}"
        else:
            prompt = (f"{self.style}. The SAME person as in the reference picture - identical face, hair, body and "
                      f"clothes - same pose, same framing, same plain grey background. Only the face changes: "
                      f"{EXPR_TEXT.get(expr, expr)}.")
        for attempt in range(3):
            try:
                data = self.image_fn(prompt, ref_path, int(rec.get("seed", 1)) + attempt * 97, 576, 1024)
                raw = self._local(f"_raw_{rec['id']}_{expr}.img")
                with open(raw, "wb") as f:
                    f.write(data)
                img = key_out(Image.open(raw))
                if np.asarray(img)[..., 3].mean() < 8:
                    raise RuntimeError("empty cut-out")
                self.stats["images_made"] += 1
                return img
            except Exception as e:
                self.stats["image_fail"] += 1
                self.log(f"  {rec['id']}/{expr} picture attempt {attempt + 1}: {str(e)[:120]}")
                if "limit" in str(e).lower() or "4006" in str(e):
                    break
        return None

    def sprites(self, rec):
        """{expression: RGBA PIL image} for a photo character (only what really exists)"""
        out = {}
        for e, r in rec.get("expr", {}).items():
            p = self._fetch(r)
            if p:
                try:
                    out[e] = Image.open(p).convert("RGBA")
                except Exception:
                    pass
        if "neutral" not in out and "reference" in out:
            out["neutral"] = out["reference"]
        return out

    # -------------------------------------------------------------- backgrounds
    def background(self, place, setting="", mood="", seed=1, w=1024, h=576):
        """an EMPTY location (no people) for this place - made once, reused by every story that comes back here"""
        key = slug(f"{place}-{setting}")[:60]
        rec = self.index["backgrounds"].get(key)
        if rec:
            p = self._fetch(rec)
            if p:
                self.stats["bg_hits"] += 1
                return p, key
        if self.image_fn:
            prompt = (f"{self.style}. Empty location, absolutely NO people, no figures, no faces: {place}. {setting}. "
                      f"Wide establishing shot at eye level, open ground in the lower half where people could stand, "
                      f"{mood or 'eerie'} night atmosphere.")
            for attempt in range(2):
                try:
                    data = self.image_fn(prompt, None, seed + attempt * 131, w, h)
                    p = self._local(f"bg_{key}.jpg")
                    with open(p, "wb") as f:
                        f.write(data)
                    Image.open(p).convert("RGB").save(p, quality=92)
                    self.index["backgrounds"][key] = dict(self._store(Image.open(p).convert("RGB"), f"bg_{key}.jpg"),
                                                          place=place, created=dt.date.today().isoformat())
                    self.stats["bg_made"] += 1
                    self.save()
                    return p, key
                except Exception as e:
                    self.log(f"  background '{place}' attempt {attempt + 1}: {str(e)[:120]}")
        p = self._local(f"bg_proc_{key}.jpg")
        procedural_background(place, setting, seed).save(p, quality=92)
        return p, key + "-procedural"


def procedural_background(place, setting="", seed=1, w=1280, h=720):
    """a night scene drawn by code (sky, moon, tree line, a house / station shape) - the last fallback"""
    rng = np.random.default_rng(int(hashlib.sha1(f"{place}{setting}{seed}".encode()).hexdigest()[:8], 16))
    y = np.linspace(0, 1, h)[:, None]
    sky = np.dstack([18 + 30 * y, 22 + 34 * y, 34 + 40 * y]) * np.ones((1, w, 1))
    img = Image.fromarray(np.clip(sky, 0, 255).astype(np.uint8))
    from PIL import ImageDraw
    d = ImageDraw.Draw(img)
    mx, my = int(w * rng.uniform(0.6, 0.85)), int(h * rng.uniform(0.12, 0.25))
    d.ellipse([mx - 38, my - 38, mx + 38, my + 38], fill=(214, 220, 210))
    hz = int(h * 0.62)
    pts = [(0, hz)]
    for x in range(0, w + 40, 40):
        pts.append((x, hz - int(rng.uniform(30, 120))))
    pts += [(w, h), (0, h)]
    d.polygon(pts, fill=(10, 12, 16))
    low = str(f"{place} {setting}").lower()
    if any(k in low for k in ("house", "rajbari", "haveli", "bari", "mansion", "bungalow")):
        bx = int(w * rng.uniform(0.15, 0.45))
        d.polygon([(bx, hz - 140), (bx + 260, hz - 140), (bx + 260, hz + 20), (bx, hz + 20)], fill=(8, 9, 12))
        d.polygon([(bx - 20, hz - 140), (bx + 130, hz - 220), (bx + 280, hz - 140)], fill=(8, 9, 12))
        d.rectangle([bx + 110, hz - 90, bx + 140, hz - 60], fill=(120, 90, 40))
    if any(k in low for k in ("station", "rail", "junction", "platform")):
        d.rectangle([0, hz + 30, w, hz + 44], fill=(30, 30, 34))
        for x in range(0, w, 90):
            d.rectangle([x, hz - 150, x + 10, hz + 30], fill=(14, 14, 18))
    d.rectangle([0, int(h * 0.8), w, h], fill=(14, 15, 18))
    return img.filter(ImageFilter.GaussianBlur(0.8))
