"""AUTOMATIC PAINTED 2D CHARACTER, BACKGROUND & PROP CREATOR + ASSET LIBRARY - zero cost.

* Painted 2D Style (default): high-end dark Bengali horror animated TV series art with crisp dark
  hand-inked outlines, rich atmospheric cel-shading, and moody low-key lighting (never flat vector shapes).
* Character ID: stable per character. Series characters keep one ID forever (taranath, bapi, nilkantha...);
  a one-story character gets <name>-<story date>. The same ID is never made twice - it is taken from the library.
* Assets ("photo" painted 2D mode, free Cloudflare picture model):
    reference  - full body, plain grey studio background (the identity every other picture copies)
    neutral / talking / fear / shock / blink / sad / angry
  each turned into a transparent PNG (border flood-fill + connected component cleanup),
  with its face box for real expression & lip-sync patch blending.
* Props ("prop" transparent PNGs): story-specific objects (hanging saree, lantern, diary, lock, etc.)
  drawn on plain studio grey and keyed out into crisp transparent RGBA sprites.
* Backgrounds ("background" empty 2D locations): painted 2D environments with ZERO people/faces.
* Dual Storage: assets/characters/index.json + compact local copies in assets/characters/store/
  (committed to git by the 2 AM / 4 AM asset runs so 2 PM / 8 PM video runs load them in 0 seconds)
  PLUS GitHub Release "characters" backup.
"""
import datetime as dt
import hashlib
import json
import os
import re

import numpy as np
from PIL import Image, ImageFilter

import silhouette

PAINTED_2D_STYLE = (
    "2D painted Bengali horror cartoon illustration, high-end animated TV series film art, "
    "crisp dark hand-inked outlines, rich atmospheric cel-shading with painted depth, "
    "dark moody low-key lighting, cold midnight blue and teal shadows with warm flickering amber lantern light, "
    "expressive stylized Indian Bengali characters and authentic Bengal architecture, "
    "no 3D render, no photorealism, no text, no letters, no watermark"
)

BASE_SET = ("neutral", "talking", "blink", "fear", "shock")
EXTRA_SET = ("sad", "angry", "happy")
EXPR_TEXT = {
    "neutral": "calm neutral face, mouth closed, eyes open looking slightly toward the side",
    "talking": "speaking clearly, mouth open mid-syllable as if saying 'aa', eyes open, identical head angle",
    "blink": "eyes gently closed with eyelids shut, mouth closed, calm, identical head angle",
    "fear": "terrified expression, eyes wide open in dread, eyebrows raised, mouth slightly open",
    "shock": "shocked gasping expression, mouth wide open in terror, eyes very wide",
    "sad": "sad sorrowful expression, eyes lowered, mouth closed",
    "angry": "angry intense expression, eyebrows furrowed down, jaw tight",
    "happy": "gentle subtle smile, eyes soft",
}
STUDIO = ("plain flat light-grey studio background (#b8b8b8), even soft frontal light, full body visible from head to feet, "
          "standing, three-quarter view, arms naturally positioned, nothing else in the picture")

PROP_STUDIO = ("plain flat light-grey studio background (#b8b8b8), even soft light, single isolated object centered "
               "with wide empty margins all around, NO people, NO hands, NO faces, NO background room or scenery, "
               "no floor shadow, nothing else in the picture")

_SOFT_MAP = {
    "blood-stained": "crimson-stained", "bloody": "crimson-stained", "blood": "crimson stain",
    "corpse": "still figure", "dead body": "lifeless figure", "dead": "lifeless-looking",
    "kill": "chase", "killed": "gone", "murder": "mystery", "knife": "old iron key",
    "skull": "weathered stone", "demon": "shadowy figure", "gore": "dark shadow", "gory": "dark",
    "hanging": "suspended", "noose": "thick jute rope", "severed": "broken",
}


def soften_prompt(prompt):
    out = str(prompt)
    for k, v in _SOFT_MAP.items():
        out = re.sub(rf"\b{re.escape(k)}\b", v, out, flags=re.I)
    return out


def slug(s):
    s = re.sub(r"[^a-z0-9]+", "-", str(s or "").lower()).strip("-")
    return s[:40] or "x"


def char_id(c, series=None, story_key=""):
    """stable ID: series characters forever, others per story"""
    base = slug(c.get("id") or c.get("name"))
    return base if series else f"{base}-{slug(story_key)}" if story_key else base


def bible(c, cid):
    look = str(c.get("look", "")).strip()
    kind = str(c.get("kind", "human")).lower()
    gender = "woman" if str(c.get("gender", "")).startswith("f") else "man"
    age = str(c.get("age", "adult")).strip()
    return {
        "id": cid,
        "name": c.get("name", cid),
        "gender": c.get("gender", ""),
        "age": age,
        "kind": kind,
        "look": look,
        "prompt": (
            f"ONE {'eerie ghostly pale ' if kind.startswith('ghost') else ''}"
            f"{age} Bengali {gender} from West Bengal, India: {look}. "
            f"Painted 2D animated series character design."
        ),
    }


def key_out(rgb, tol=34.0, keep_components=1):
    """Border flood-fill background removal -> clean RGBA PNG (never punches holes inside white clothes/eyes)."""
    import cv2
    arr = np.asarray(rgb.convert("RGB"), dtype=np.uint8)
    h, w = arr.shape[:2]
    lab = cv2.cvtColor(arr, cv2.COLOR_RGB2LAB).astype(np.int16)
    border = np.concatenate([lab[:4].reshape(-1, 3), lab[-4:].reshape(-1, 3),
                             lab[:, :4].reshape(-1, 3), lab[:, -4:].reshape(-1, 3)])
    bg = np.median(border, axis=0)
    dist = np.sqrt(((lab - bg) ** 2).sum(axis=2))
    bg_cand = (dist < tol).astype(np.uint8)

    flood = np.zeros((h, w), np.uint8)
    seeds = ([(x, 0) for x in range(0, w, 8)] + [(x, h - 1) for x in range(0, w, 8)] +
             [(0, y) for y in range(0, h, 8)] + [(w - 1, y) for y in range(0, h, 8)])
    for sx, sy in seeds:
        if bg_cand[sy, sx] and not flood[sy, sx]:
            m = np.zeros((h + 2, w + 2), np.uint8)
            cv2.floodFill(bg_cand.copy(), m, (sx, sy), 128, loDiff=0, upDiff=0,
                          flags=4 | (255 << 8) | cv2.FLOODFILL_MASK_ONLY)
            flood |= m[1:-1, 1:-1]

    alpha = np.where(flood > 0, 0.0, 1.0).astype(np.float32)
    fg_bin = (alpha > 0.5).astype(np.uint8)
    n, lab_cc, stats, _ = cv2.connectedComponentsWithStats(fg_bin, 8)
    if n > 1:
        areas = [(i, int(stats[i, cv2.CC_STAT_AREA])) for i in range(1, n)]
        areas.sort(key=lambda t: -t[1])
        keep_ids = {i for i, ar in areas[:max(1, keep_components)] if ar >= 120}
        if keep_ids:
            keep_mask = np.isin(lab_cc, list(keep_ids)).astype(np.uint8)
            keep_mask = cv2.dilate(keep_mask, np.ones((5, 5), np.uint8))
            alpha *= keep_mask.astype(np.float32)

    alpha = cv2.GaussianBlur(alpha, (0, 0), 1.0)
    out = np.dstack([arr.astype(np.float32), np.clip(alpha * 255.0, 0, 255)]).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def face_box(rgba):
    """Find face box via OpenCV Haar cascade, with anatomical head-region fallback for stylized 2D painted art."""
    try:
        import animate
        f = animate.find_faces(np.asarray(rgba.convert("RGB")))
        if f:
            return list(max(f, key=lambda x: x["box"][2])["box"])
    except Exception:
        pass
    a = np.asarray(rgba)[..., 3] > 127
    ys, xs = np.where(a)
    if len(ys) < 200:
        return None
    x0, y0, x1, y1 = int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())
    bw, bh = x1 - x0, y1 - y0
    if bw < 30 or bh < 80:
        return None
    head_y1 = y0 + max(20, int(0.22 * bh))
    hys, hxs = np.where(a[y0:head_y1, x0:x1])
    if len(hxs) < 40:
        return [x0 + int(0.28 * bw), y0 + int(0.03 * bh), max(24, int(0.44 * bw)), max(24, int(0.16 * bh))]
    hx0 = x0 + int(hxs.min())
    hx1 = x0 + int(hxs.max())
    fw = max(24, hx1 - hx0)
    fh = max(24, head_y1 - y0)
    return [hx0, y0 + int(0.02 * bh), fw, fh]


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
    """Zero-cost Painted 2D Character, Background & Prop Asset Library."""

    def __init__(self, assets_dir, cache_dir, image_fn=None, upload_fn=None, log=print, style=""):
        self.dir = os.path.join(assets_dir, "characters")
        self.store_dir = os.path.join(self.dir, "store")
        self.cache = cache_dir
        os.makedirs(self.cache, exist_ok=True)
        os.makedirs(self.store_dir, exist_ok=True)
        self.index_path = os.path.join(self.dir, "index.json")
        try:
            with open(self.index_path, encoding="utf-8") as f:
                self.index = json.load(f)
        except Exception:
            self.index = {"chars": {}, "backgrounds": {}, "props": {}}
        self.index.setdefault("chars", {})
        self.index.setdefault("backgrounds", {})
        self.index.setdefault("props", {})
        self.image_fn = image_fn
        self.upload_fn = upload_fn
        self.log = log
        self.style = style or PAINTED_2D_STYLE
        self.stats = {
            "images_made": 0, "image_fail": 0, "cache_hits": 0,
            "silhouettes": 0, "bg_made": 0, "bg_hits": 0,
            "props_made": 0, "props_hits": 0,
        }

    def save(self):
        os.makedirs(self.dir, exist_ok=True)
        with open(self.index_path, "w", encoding="utf-8") as f:
            json.dump(self.index, f, ensure_ascii=False, indent=1)

    def _local(self, name):
        return os.path.join(self.cache, name)

    def _repo_store(self, name):
        return os.path.join(self.store_dir, name)

    def _fetch(self, rec):
        if not isinstance(rec, dict) or not rec.get("file"):
            return None
        fname = rec["file"]
        p_cache = self._local(fname)
        if os.path.exists(p_cache) and os.path.getsize(p_cache) > 200:
            return p_cache
        p_store = self._repo_store(fname)
        if os.path.exists(p_store) and os.path.getsize(p_store) > 200:
            try:
                import shutil
                shutil.copy2(p_store, p_cache)
                return p_cache
            except Exception:
                return p_store
        url = rec.get("url")
        if url:
            try:
                import requests
                r = requests.get(url, timeout=120)
                if r.ok and len(r.content) > 500:
                    with open(p_cache, "wb") as f:
                        f.write(r.content)
                    return p_cache
            except Exception as e:
                self.log("  character asset not downloaded:", str(e)[:100])
        return None

    def _store(self, img, name, is_jpeg=False):
        p_cache = self._local(name)
        p_store = self._repo_store(name)
        if is_jpeg:
            img.convert("RGB").save(p_cache, quality=88, optimize=True)
            img.convert("RGB").save(p_store, quality=88, optimize=True)
        else:
            img.save(p_cache, optimize=True)
            img.save(p_store, optimize=True)
        url = ""
        if self.upload_fn:
            try:
                url = self.upload_fn(p_cache, name) or ""
            except Exception as e:
                self.log("  asset not uploaded to release (saved locally in repo store):", str(e)[:100])
        return {"file": name, "url": url}

    def get(self, cid):
        return self.index["chars"].get(cid)

    def ensure(self, c, cid, need=BASE_SET, seed=1):
        rec = self.index["chars"].get(cid)
        if rec is None:
            rec = {
                "id": cid, "version": 1, "bible": bible(c, cid),
                "mode": None, "expr": {},
                "created": dt.date.today().isoformat(), "seed": seed,
            }
            self.index["chars"][cid] = rec
        else:
            self.stats["cache_hits"] += 1
        rec["last_used"] = dt.date.today().isoformat()
        if rec.get("mode") == "silhouette" and self.image_fn and rec.get("retry_photo", True):
            rec["mode"] = None
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
                self.log(f"  {rec['id']}: no face region found on reference - silhouette instead")
                return False
            rec["expr"]["reference"] = dict(self._store(img, f"{rec['id']}_v{rec['version']}_reference.png"), face=fb)
            rec["mode"] = "photo"
            rec["provider"] = "cloudflare"
            self.save()
        rec["mode"] = "photo"
        ref_p = self._fetch(rec["expr"]["reference"])
        for e in need:
            if e in rec["expr"] and self._fetch(rec["expr"][e]):
                continue
            if not self.image_fn:
                continue
            img = self._make(rec, e, ref_p)
            if img is None:
                continue
            fb = face_box(img)
            rfb = rec["expr"]["reference"].get("face")
            if not fb or (rfb and abs((fb[0] + fb[2] / 2) - (rfb[0] + rfb[2] / 2)) > 0.38 * rfb[2]):
                self.log(f"  {rec['id']}/{e}: face shifted too far - keeping neutral base for this expression")
                self.stats["image_fail"] += 1
                continue
            sim = _hist_sim(Image.open(ref_p), img)
            rec["expr"][e] = dict(self._store(img, f"{rec['id']}_v{rec['version']}_{e}.png"), face=fb,
                                  similarity=round(sim, 3))
            self.save()
        return True

    def _make(self, rec, expr, ref_path):
        b = rec["bible"]
        if expr == "reference":
            prompt = f"{self.style}. Painted 2D character model sheet. {b['prompt']} {STUDIO}"
        else:
            prompt = (
                f"{self.style}. The EXACT SAME painted 2D character as in the reference image - identical face, hair, "
                f"body and clothes - identical standing pose, framing and plain flat light-grey background. "
                f"Only the facial expression changes: {EXPR_TEXT.get(expr, expr)}."
            )
        for attempt in range(3):
            p_try = soften_prompt(prompt) if attempt >= 1 else prompt
            try:
                data = self.image_fn(p_try, ref_path, int(rec.get("seed", 1)) + attempt * 97, 576, 1024)
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
                self.log(f"  {rec['id']}/{expr} attempt {attempt + 1}: {str(e)[:120]}")
                if any(k in str(e).lower() for k in ("limit", "4006", "quota", "neurons")):
                    break
        return None

    def sprites(self, rec):
        """{expression: RGBA PIL image} for a painted 2D character."""
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

    def background(self, place, setting="", mood="", seed=1, w=1024, h=576):
        """An EMPTY painted 2D location background (NO people/faces) - made once, reused everywhere."""
        key = slug(f"{place}-{setting}")[:60]
        rec = self.index["backgrounds"].get(key)
        if rec:
            p = self._fetch(rec)
            if p:
                self.stats["bg_hits"] += 1
                return p, key
        if self.image_fn:
            prompt = (
                f"{self.style}. Empty painted 2D background environment illustration only, absolutely NO people, "
                f"NO characters, NO figures, NO faces: {place}. {setting}. "
                f"Wide establishing shot at eye level, clear open floor/ground in the lower half where characters can stand, "
                f"{mood or 'eerie'} horror atmosphere."
            )
            for attempt in range(2):
                p_try = soften_prompt(prompt) if attempt >= 1 else prompt
                try:
                    data = self.image_fn(p_try, None, seed + attempt * 131, w, h)
                    raw_p = self._local(f"_raw_bg_{key}.img")
                    with open(raw_p, "wb") as f:
                        f.write(data)
                    im = Image.open(raw_p).convert("RGB")
                    stored = self._store(im, f"bg_{key}.jpg", is_jpeg=True)
                    self.index["backgrounds"][key] = dict(stored, place=place, created=dt.date.today().isoformat())
                    self.stats["bg_made"] += 1
                    self.save()
                    return self._fetch(self.index["backgrounds"][key]), key
                except Exception as e:
                    self.log(f"  background '{place}' attempt {attempt + 1}: {str(e)[:120]}")
                    if any(k in str(e).lower() for k in ("limit", "4006", "quota", "neurons")):
                        break
        p = self._local(f"bg_proc_{key}.jpg")
        procedural_background(place, setting, seed).save(p, quality=92)
        return p, key + "-procedural"

    def prop(self, prop_name, prop_desc="", seed=1):
        """Generate or load a transparent RGBA PNG sprite for a specific story prop (e.g. hanging saree, lantern)."""
        key = slug(prop_name)[:48]
        rec = self.index["props"].get(key)
        if rec:
            p = self._fetch(rec)
            if p:
                self.stats["props_hits"] += 1
                return p, key
        if not self.image_fn:
            return None, key
        desc = (prop_desc or prop_name).strip()
        prompt = f"{self.style}. Painted 2D animated prop illustration of: {desc}. {PROP_STUDIO}"
        for attempt in range(2):
            p_try = soften_prompt(prompt) if attempt >= 1 else prompt
            try:
                data = self.image_fn(p_try, None, seed + attempt * 73, 512, 512)
                raw_p = self._local(f"_raw_prop_{key}.img")
                with open(raw_p, "wb") as f:
                    f.write(data)
                rgba = key_out(Image.open(raw_p), tol=32.0, keep_components=2)
                alpha_mean = float(np.asarray(rgba)[..., 3].mean())
                if alpha_mean < 4.0 or alpha_mean > 220.0:
                    raise RuntimeError(f"bad prop cutout coverage ({alpha_mean:.1f})")
                a = np.asarray(rgba)[..., 3] > 60
                ys, xs = np.where(a)
                if len(ys) < 20:
                    raise RuntimeError("prop empty after crop")
                rgba = rgba.crop((max(0, int(xs.min()) - 4), max(0, int(ys.min()) - 4),
                                  min(rgba.width, int(xs.max()) + 5), min(rgba.height, int(ys.max()) + 5)))
                stored = self._store(rgba, f"prop_{key}.png", is_jpeg=False)
                self.index["props"][key] = dict(stored, name=prop_name, desc=desc, created=dt.date.today().isoformat())
                self.stats["props_made"] += 1
                self.save()
                return self._fetch(self.index["props"][key]), key
            except Exception as e:
                self.log(f"  prop '{prop_name}' attempt {attempt + 1}: {str(e)[:120]}")
                if any(k in str(e).lower() for k in ("limit", "4006", "quota", "neurons")):
                    break
        return None, key


def procedural_background(place, setting="", seed=1, w=1280, h=720):
    """Painted-look night scene fallback when offline or quota-limited."""
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
    if any(k in low for k in ("house", "rajbari", "haveli", "bari", "mansion", "bungalow", "room", "interior", "ghar")):
        bx = int(w * rng.uniform(0.15, 0.45))
        d.polygon([(bx, hz - 140), (bx + 260, hz - 140), (bx + 260, hz + 20), (bx, hz + 20)], fill=(14, 15, 20))
        d.polygon([(bx - 20, hz - 140), (bx + 130, hz - 220), (bx + 280, hz - 140)], fill=(10, 11, 16))
        d.rectangle([bx + 110, hz - 90, bx + 140, hz - 60], fill=(150, 105, 42))
    if any(k in low for k in ("station", "rail", "junction", "platform")):
        d.rectangle([0, hz + 30, w, hz + 44], fill=(30, 30, 34))
        for x in range(0, w, 90):
            d.rectangle([x, hz - 150, x + 10, hz + 30], fill=(14, 14, 18))
    d.rectangle([0, int(h * 0.8), w, h], fill=(14, 15, 18))
    return img.filter(ImageFilter.GaussianBlur(0.8))
