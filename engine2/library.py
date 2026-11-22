"""PERMANENT CHARACTER ASSET LIBRARY (engine 2, stage 2).

Every character gets a permanent identity and VERSIONED, reusable assets, made ONCE and reused by every future story
(no character image generation at render time). Layout (in the repository, so it is versioned by git as well):

  assets/character_library/
    APPROVALS.json                 <- ONLY the owner writes this (by hand on GitHub). The code never approves anything.
    <id>/manifest.json             <- the character's manifest (fields below), rebuilt by sync()
    <id>/v1/reference/original.png (+ original_src.png)   the ORIGINAL Cloudflare reference (copied, never changed)
    <id>/v1/poses/<pose>.png       complete-pose drawings (method B: front, side, stand, sit, talk, point, walk1-4)
    <id>/v1/parts/<part>.png       separated body parts + rig.json (method A, cut from the FRONT drawing)
    <id>/v1/version.json           every asset: file, sha256, status, problems, provider, model, source, time
    <id>/rejected/                 a replaced or rejected candidate is MOVED here, never deleted

Asset statuses (kept apart, as required):
  GENERATED              the file exists
  TECHNICALLY_VALID      it passed the technical checks (readable RGBA, a figure, not cut by the edge, right size)
  VISUAL_REVIEW_REQUIRED valid, waiting for the owner's eyes (this is the best the CODE can ever give)
  USER_APPROVED          only from APPROVALS.json
  REJECTED               failed a technical check, or rejected by the owner
A version is IMMUTABLE once the owner approved it: a different file for the same asset goes into a NEW version
(the approved one stays as it is). Before approval, missing assets are added to the current version; a CHANGED
file for an existing asset also opens a new version (nothing is overwritten).
"""
import datetime as dt
import hashlib
import json
import os
import shutil

import cv2
import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARTS_ROOT = os.path.join(HERE, "assets", "cartoon_parts")     # where the existing (first-test) assets live
LIB = os.path.join(HERE, "assets", "character_library")

GENERATED, VALID, REVIEW, APPROVED, REJECTED = ("GENERATED", "TECHNICALLY_VALID", "VISUAL_REVIEW_REQUIRED",
                                                "USER_APPROVED", "REJECTED")
POSES = ["front", "side", "stand", "sit", "talk", "point", "walk1", "walk2", "walk3", "walk4"]
PARTS_LEGS = ["head", "torso", "uarm_near", "farm_near", "uarm_far", "farm_far", "thigh_near", "shin_near",
              "thigh_far", "shin_far"]
PARTS_CLOTH = ["head", "torso", "uarm_near", "farm_near", "uarm_far", "farm_far", "skirt_up", "skirt_lo"]
EXPRESSIONS_WANTED = ["neutral", "talking", "happy", "sad", "angry", "surprised", "laughing", "crying"]


def _now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 16), b""):
            h.update(b)
    return h.hexdigest()


def _jload(path, default):
    try:
        return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else default
    except Exception:
        return default


def _jsave(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1, default=str)
    os.replace(tmp, path)


def char_id(name):
    return "".join(ch for ch in str(name).lower() if ch.isalnum() or ch == "_")


# ------------------------------------------------------------------------------------------------ approvals
def approvals():
    """APPROVALS.json - written ONLY by the owner. Format:
    {"hari": {"v1": {"status": "USER_APPROVED" | "REJECTED", "method": "full_pose" | "cutout", "note": "..."}}}"""
    a = _jload(os.path.join(LIB, "APPROVALS.json"), {})
    return {k: v for k, v in a.items() if not k.startswith("_")} if isinstance(a, dict) else {}


def owner_decision(cid, version):
    d = (approvals().get(cid) or {}).get(version) or {}
    st = str(d.get("status", "")).upper()
    return {"status": st if st in (APPROVED, REJECTED) else None, "method": d.get("method"), "note": d.get("note")}


def ensure_approvals_file():
    """create the file once, with instructions only (never with an approval in it)"""
    f = os.path.join(LIB, "APPROVALS.json")
    if not os.path.exists(f):
        _jsave(f, {"_how_to": "Only YOU edit this file (on GitHub: open it, the pencil, Commit). Example: "
                              "\"hari\": {\"v1\": {\"status\": \"USER_APPROVED\", \"method\": \"full_pose\", \"note\": "
                              "\"looked at the sheet on 23 Nov\"}}  - status USER_APPROVED or REJECTED; method full_pose "
                              "(complete drawings) or cutout (separated parts). Nothing is used in a video before this."})
    return f


# ------------------------------------------------------------------------------------------------ technical checks
def technical_check(path, kind):
    """technical QA only (never artistic): readable, RGBA with a real figure, not cut by the edge, sane size"""
    probs = []
    img = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if img is None:
        return ["the file cannot be read"], {}
    m = {"w": int(img.shape[1]), "h": int(img.shape[0])}
    if kind == "reference_src":                             # (the untouched provider picture: no transparency by nature)
        return ([] if min(img.shape[:2]) >= 256 else ["too small"]), m
    if img.ndim < 3 or img.shape[2] != 4:
        return probs + ["no transparency (RGBA expected)"], m
    a = img[..., 3] > 127
    cover = float(a.mean())
    m["coverage"] = round(cover, 3)
    if cover < 0.01:
        probs.append("almost empty (no figure)")
    if kind in ("reference", "pose") and cover > 0:
        ys, xs = np.where(a)
        H, W = a.shape
        if ys.min() <= 1 or ys.max() >= H - 2 or xs.min() <= 1 or xs.max() >= W - 2:
            probs.append("the figure touches the picture edge (something may be cut off)")
        if kind == "reference" and (ys.max() - ys.min()) < 0.5 * H:
            probs.append("the figure is too small in the picture")
    if min(img.shape[:2]) < 24:
        probs.append(f"too small ({img.shape[1]}x{img.shape[0]})")
    return probs, m


# ------------------------------------------------------------------------------------------------ one character
class Character:
    def __init__(self, name, key=None):
        self.name, self.id, self.key = name, char_id(name), key
        self.dir = os.path.join(LIB, self.id)
        self.manifest_f = os.path.join(self.dir, "manifest.json")
        self.manifest = _jload(self.manifest_f, {})

    # versions -----------------------------------------------------------------
    def versions(self):
        return sorted([d for d in os.listdir(self.dir) if d.startswith("v") and d[1:].isdigit()],
                      key=lambda v: int(v[1:])) if os.path.isdir(self.dir) else []

    def current(self):
        vs = self.versions()
        return vs[-1] if vs else None

    def _vfile(self, v):
        return os.path.join(self.dir, v, "version.json")

    def _vdata(self, v):
        return _jload(self._vfile(v), {"version": v, "created": _now(), "assets": {}})

    def _new_version(self, copy_from=None):
        vs = self.versions()
        v = f"v{(int(vs[-1][1:]) + 1) if vs else 1}"
        os.makedirs(os.path.join(self.dir, v), exist_ok=True)
        data = {"version": v, "created": _now(), "assets": {}, "derived_from": copy_from}
        if copy_from:                                       # unchanged assets are carried over (as files)
            old = self._vdata(copy_from)
            for aid, e in old["assets"].items():
                src = os.path.join(self.dir, copy_from, e["file"])
                dst = os.path.join(self.dir, v, e["file"])
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                if os.path.exists(src):
                    shutil.copy2(src, dst)
                    data["assets"][aid] = dict(e, carried_from=copy_from)
        _jsave(self._vfile(v), data)
        return v

    def frozen(self, v):
        return owner_decision(self.id, v)["status"] == APPROVED

    # adding assets --------------------------------------------------------------
    def add(self, aid, src_path, rel_file, kind, provider=None, model=None, source=None):
        """put ONE asset into the library: never overwrites; a changed file -> a new version; an approved version is
        never changed. Returns (version, status)."""
        if not os.path.exists(src_path):
            return None, "missing"
        v = self.current() or self._new_version()
        data = self._vdata(v)
        h = sha256(src_path)
        e = data["assets"].get(aid)
        if e and e.get("sha256") == h:
            return v, e["status"]                           # already there, identical: nothing to do
        if e or self.frozen(v):                             # a DIFFERENT file for an existing asset, or the current
            v = self._new_version(copy_from=v)              # version is approved -> a NEW version, the old stays
            data = self._vdata(v)
            old = data["assets"].pop(aid, None)
            if old:
                rej = os.path.join(self.dir, "rejected", f"{aid}_{old.get('sha256', '')[:8]}{os.path.splitext(old['file'])[1]}")
                os.makedirs(os.path.dirname(rej), exist_ok=True)
                prev = os.path.join(self.dir, v, old["file"])
                if os.path.exists(prev):
                    shutil.move(prev, rej)                  # (the replaced candidate is kept, not deleted)
        dst = os.path.join(self.dir, v, rel_file)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src_path, dst)
        probs, meta = technical_check(dst, kind) if rel_file.endswith(".png") else ([], {})
        status = REJECTED if probs else REVIEW              # (valid -> waiting for the owner; never more)
        data["assets"][aid] = {"file": rel_file, "kind": kind, "sha256": h, "status": status, "technical": meta,
                               "problems": probs, "provider": provider, "model": model, "source": source,
                               "added": _now()}
        _jsave(self._vfile(v), data)
        return v, status

    # integrity --------------------------------------------------------------------
    def verify(self, v=None):
        """every file of a version is there and unchanged (sha256)"""
        v = v or self.current()
        out = {"version": v, "missing": [], "corrupt": []}
        if not v:
            return out
        for aid, e in self._vdata(v)["assets"].items():
            f = os.path.join(self.dir, v, e["file"])
            if not os.path.exists(f):
                out["missing"].append(aid)
            elif sha256(f) != e["sha256"]:
                out["corrupt"].append(aid)
        return out

    # what is missing / usable ----------------------------------------------------------
    def build_manifest(self, design=None, rig_meta=None):
        v = self.current()
        data = self._vdata(v) if v else {"assets": {}}
        A = data["assets"]
        dec = owner_decision(self.id, v) if v else {"status": None}
        no_legs = bool((rig_meta or {}).get("no_legs"))
        parts_needed = PARTS_CLOTH if no_legs else PARTS_LEGS
        have_pose = [p for p in POSES if A.get(f"pose:{p}", {}).get("status") in (REVIEW, APPROVED)]
        have_part = [p for p in parts_needed if A.get(f"part:{p}", {}).get("status") in (REVIEW, APPROVED)]
        missing = (["reference"] if "reference" not in A else []) + [f"pose:{p}" for p in POSES if p not in have_pose] + \
            [f"part:{p}" for p in parts_needed if p not in have_part]
        integ = self.verify(v)
        st_counts = {}
        for e in A.values():
            st_counts[e["status"]] = st_counts.get(e["status"], 0) + 1
        if integ["missing"] or integ["corrupt"]:
            validation = "BROKEN - " + ", ".join(integ["missing"] + integ["corrupt"])
        elif any(e["status"] == REJECTED for e in A.values()):
            validation = "SOME ASSETS FAILED THE TECHNICAL CHECK"
        elif A:
            validation = "TECHNICALLY VALID - VISUAL REVIEW REQUIRED" if dec["status"] != APPROVED else "USER APPROVED"
        else:
            validation = "EMPTY"
        rm = rig_meta or {}
        self.manifest = {
            "character_id": self.id, "name": self.name, "registry_key": self.key, "asset_version": v,
            "versions": self.versions(),
            "original_reference": (os.path.join(v, A["reference"]["file"]) if v and "reference" in A else None),
            "approval_status": dec["status"] or "NOT APPROVED (waiting for the owner)",
            "approved_method": dec["method"] if dec["status"] == APPROVED else None,
            "body_proportions": rm.get("measures"), "head_fraction": rm.get("head_fraction"),
            "layer_order": rm.get("layers"),
            "joint_coordinates": {k: rm.get(k) for k in ("neck", "hip", "shoulders", "leg_hips") if k in rm} or None,
            "anchor_points": {k: rm.get(k) for k in ("waist", "pallu_anchor", "hair_anchor") if k in rm} or None,
            "available_poses": have_pose,
            "available_parts": have_part,
            "available_expressions": (["neutral"] if "reference" in A else []) +
                                     (["talking"] if "pose:talk" in have_pose or have_part else []),
            "missing_expressions": [x for x in EXPRESSIONS_WANTED if x not in ("neutral", "talking")],
            "missing_assets": missing,
            "validation_status": validation, "status_counts": st_counts, "integrity": integ,
            "props": [a for a in A if a.startswith("prop:")],
            "design": design, "updated": _now()}
        _jsave(self.manifest_f, self.manifest)
        return self.manifest

    def render_assets(self):
        """what a VIDEO may use: ONLY an owner-approved version with all assets of its method present and valid.
        Returns (assets, None) or (None, the reason). No image generation ever happens here."""
        v = self.current()
        if not v:
            return None, "no assets"
        # the newest APPROVED version (a later unapproved candidate never replaces it)
        for vv in reversed(self.versions()):
            dec = owner_decision(self.id, vv)
            if dec["status"] == APPROVED:
                v = vv
                break
        else:
            return None, "not approved by the owner"
        dec = owner_decision(self.id, v)
        A = self._vdata(v)["assets"]
        integ = self.verify(v)
        if integ["missing"] or integ["corrupt"]:
            return None, "approved version damaged: " + ", ".join(integ["missing"] + integ["corrupt"])
        method = dec["method"] or "full_pose"
        if method == "full_pose":
            need = [f"pose:{p}" for p in POSES]
        else:
            need = [f"part:{p}" for p in PARTS_LEGS] if "part:thigh_near" in A else [f"part:{p}" for p in PARTS_CLOTH]
        bad = [n for n in need if A.get(n, {}).get("status") not in (REVIEW, APPROVED)]
        if bad:
            return None, "approved version is missing: " + ", ".join(bad)
        return {"version": v, "method": method, "dir": os.path.join(self.dir, v),
                "files": {k: os.path.join(self.dir, v, e["file"]) for k, e in A.items()}}, None


# ------------------------------------------------------------------------------------------------ sync from the project
def known_characters():
    """the characters the project already has assets for (assets/cartoon_parts/index.json)"""
    idx = _jload(os.path.join(PARTS_ROOT, "index.json"), {}).get("characters", {})
    return [(v.get("name"), k) for k, v in idx.items() if v.get("name")]


def sync(log=print):
    """bring EVERY existing asset into the library (idempotent, no image generation, nothing overwritten):
    the original reference, the char_sheet drawings that passed, the 4 walk frames, the parts cut from the front
    drawing, props. Then rebuild each manifest. Returns a report."""
    ensure_approvals_file()
    rep = {"characters": {}, "time": _now()}
    for name, key in known_characters():
        ch = Character(name, key)
        src = os.path.join(PARTS_ROOT, key)
        added = []
        for aid, f, rel, kind in (("reference", "body.png", "reference/original.png", "reference"),
                                  ("reference_src", "body_src.png", "reference/original_src.png", "reference_src")):
            if os.path.exists(os.path.join(src, f)):
                v, st = ch.add(aid, os.path.join(src, f), rel, kind, provider="cloudflare",
                               model="@cf/black-forest-labs/flux-2-klein-4b", source=f"cartoon_parts/{key}/{f}")
                added.append((aid, st))
        sheet = _jload(os.path.join(src, "sheet", "sheet.json"), {})
        for view in ("front", "side", "stand", "sit", "talk", "point"):
            f = os.path.join(src, "sheet", f"{view}.png")
            if (sheet.get(view) or {}).get("status") == "passed" and os.path.exists(f):
                added.append((f"pose:{view}", ch.add(f"pose:{view}", f, f"poses/{view}.png", "pose", provider="cloudflare",
                                                     model="@cf/black-forest-labs/flux-2-klein-4b",
                                                     source=f"cartoon_parts/{key}/sheet/{view}.png")[1]))
        if (sheet.get("walk") or {}).get("status") == "passed":
            for k in range(1, 5):
                f = os.path.join(src, "sheet", f"walk{k}.png")
                if os.path.exists(f):
                    added.append((f"pose:walk{k}", ch.add(f"pose:walk{k}", f, f"poses/walk{k}.png", "pose",
                                                          provider="cloudflare", model="@cf/black-forest-labs/flux-2-klein-4b",
                                                          source=f"cartoon_parts/{key}/sheet/walk{k}.png")[1]))
        rig_meta = None
        pd = os.path.join(src, "sheet", "parts")             # parts cut from the FRONT drawing (method A candidate)
        if os.path.exists(os.path.join(pd, "rig.json")):
            rig_meta = _jload(os.path.join(pd, "rig.json"), None)
            for pn in (rig_meta or {}).get("parts", {}):
                f = os.path.join(pd, f"part_{pn}.png")
                if os.path.exists(f):
                    added.append((f"part:{pn}", ch.add(f"part:{pn}", f, f"parts/{pn}.png", "part",
                                                       source=f"cartoon_parts/{key}/sheet/parts/part_{pn}.png")[1]))
            f = os.path.join(pd, "rig.json")
            ch.add("rig", f, "parts/rig.json", "rig", source=f"cartoon_parts/{key}/sheet/parts/rig.json")
            for i, pr in enumerate((rig_meta or {}).get("props") or []):
                f = os.path.join(pd, pr.get("file", ""))
                if os.path.exists(f):
                    added.append((f"prop:{i}", ch.add(f"prop:{i}", f, f"props/prop_{i}.png", "prop")[1]))
        if rig_meta is None:                                 # proportions measured on the ORIGINAL (technical data only)
            try:
                import asset_plan
                import puppet_builder as PB
                ref = cv2.imread(os.path.join(src, "body.png"), cv2.IMREAD_UNCHANGED)
                arch = ((_jload(os.path.join(PARTS_ROOT, "index.json"), {}).get("characters", {}).get(key) or {})
                        .get("plan") or {}).get("archetype")
                plan = dict(asset_plan.plan({}), **({"archetype": arch} if arch else {}))
                rig, _, _ = PB.build(ref, plan) if ref is not None else (None, None, None)
                if rig:
                    rig_meta = {k: v for k, v in rig.items() if k not in ("parts", "props")}
            except Exception as e:
                log(f"  library: proportions of {name} not measured ({type(e).__name__})")
        m = ch.build_manifest(rig_meta=rig_meta)
        rep["characters"][name] = {"id": ch.id, "version": m["asset_version"], "approval": m["approval_status"],
                                   "validation": m["validation_status"], "poses": m["available_poses"],
                                   "parts": m["available_parts"], "missing": m["missing_assets"],
                                   "counts": m["status_counts"]}
        log(f"  library: {name} {m['asset_version']} - {m['validation_status']}; approval: {m['approval_status']}; "
            f"{len(m['missing_assets'])} assets missing")
    _jsave(os.path.join(LIB, "library_report.json"), rep)
    return rep
