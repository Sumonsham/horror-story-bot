"""HYBRID 2D - one character, two methods, chosen per action from the assets that exist (and are approved).

  METHOD A cut-out (cutout_rig.CutoutCharacter from the library's parts): idle, breathing, blinking, talking,
           listening, looking, pointing, simple gestures, walking (IK gait), sitting (with a seat)
  METHOD B complete-pose (fullpose.FullPoseCharacter from the library's drawings): whatever drawing exists -
           stand, talk, point, sit, walk1-4 (and later: run, fall, fear, ... once such drawings are made + approved)

PRODUCTION uses only the owner-approved version (library.render_assets). PREVIEW (test modes only) may use the
technically valid candidates, and every preview frame carries 'PREVIEW - NOT APPROVED'.
An action with no asset is REPORTED (missing_for) - it is never drawn with a broken pose.
"""
import os
import tempfile

ACTIONS = {
    # action: (cut-out pose / motion it uses, complete-pose drawings it needs)
    "idle": ("stand", ["stand"]), "breathing": ("stand", ["stand"]), "blinking": ("stand", ["stand"]),
    "talking": ("stand_talk", ["stand"]), "listening": ("stand", ["stand"]), "looking_left_right": ("stand", ["stand"]),
    "pointing": ("stand_point", ["point"]), "gesture": ("stand_talk", ["talk"]),
    "walking": ("walk", ["walk1", "walk2", "walk3", "walk4"]), "sitting": ("sit", ["sit"]),
    "standing_up": ("sit->stand", ["sit", "stand"]), "turning": ("mirror", ["side"]),
    "looking_behind": ("head turn", ["side"]), "fear": ("stand_fear", ["fear"]), "running": (None, ["run1", "run2", "run3", "run4"]),
    "falling": (None, ["fall"]), "fighting": (None, ["fight"]), "waving": (None, ["wave"]), "namaste": (None, ["namaste"]),
}
EXPRESSIONS = ["neutral", "happy", "sad", "angry", "afraid", "shocked", "confused", "crying", "laughing", "suspicious",
               "thinking", "terrified"]
FULL_PREFERRED = {"walking", "sitting", "standing_up", "fear", "running", "falling", "fighting"}   # complex: drawings first


def missing_for(cut_ok, poses):
    """per action: which method can do it with the assets that exist - or what is missing"""
    out = {}
    for a, (cut, need) in ACTIONS.items():
        full_ok = all(n in poses for n in need)
        if a in FULL_PREFERRED and full_ok:
            out[a] = "full_pose"
        elif cut_ok and cut:
            out[a] = "cutout"
        elif full_ok:
            out[a] = "full_pose"
        else:
            out[a] = "MISSING: " + (", ".join(n for n in need if n not in poses) or "a drawing")
    return out


class HybridCharacter:
    """chooses, per frame, the method for what the character is doing: a complex action (walking, sitting...) uses
    the complete drawings when they exist; everything else the cut-out rig; never a method without its assets"""

    def __init__(self, cid, design, cut=None, full=None, preview=False):
        if cut is None and full is None:
            raise ValueError("no usable assets")
        self.id, self.d, self.cut, self.full, self.preview = cid, design, cut, full, preview
        self.complete = True
        self.method_log = {}

    def _pick(self, st):
        p = st.get("pose") or {}
        walking = st.get("walk_phase") is not None
        sitting = p.get("hip", 147) < 120
        if self.full is not None:
            names = self.full.poses
            if walking and all(f"walk{k}" in names for k in range(1, 5)):
                return self.full, "full_pose"
            if sitting and "sit" in names:
                return self.full, "full_pose"
            if self.cut is None:
                return self.full, "full_pose"
        return (self.cut, "cutout") if self.cut is not None else (self.full, "full_pose")

    def joints(self, st):
        return self._pick(st)[0].joints(st)

    def foot_floor(self, st):
        return self._pick(st)[0].foot_floor(st)

    def step_length(self, kind="walk"):
        ch = self.full if (self.full is not None and len(getattr(self.full, "walk", [])) == 4) else self.cut
        return ch.step_length(kind) if hasattr(ch, "step_length") else 118.0

    def draw(self, pt, st):
        ch, m = self._pick(st)
        self.method_log[m] = self.method_log.get(m, 0) + 1
        return ch.draw(pt, st)


def _cut_from_parts(cid, design, parts_dir, scale):
    import cutout_rig as CR
    if not os.path.exists(os.path.join(parts_dir, "rig.json")):
        return None
    ch = CR.CutoutCharacter(cid, design, parts_dir, scale)
    return ch if ch.complete else None


def _cut_from_reference(cid, design, ref_path, scale, plan=None):
    """PREVIEW ONLY: a puppet cut from the original reference - used only if it passes the whole assembled check"""
    import cv2
    import asset_plan
    import assembly_qa as AQ
    import cutout_assets as CA
    import cutout_rig as CR
    import puppet_builder as PB
    ref = cv2.imread(ref_path, cv2.IMREAD_UNCHANGED)
    if ref is None:
        return None, "no reference"
    plan = plan or asset_plan.plan(design)
    rig, probs, _ = PB.build(ref, plan)
    if rig is None or probs:
        return None, "; ".join(probs[:2]) or "cannot be cut"
    d = tempfile.mkdtemp(prefix=f"hyb_{cid}_")
    CA.Maker._save_rig(d, rig)
    CA.save_ref_head(d, rig)
    ch = CR.CutoutCharacter(cid, design, d, scale)
    gate = AQ.check(ch, ref, probs, plan)
    if not gate["pass"]:
        return None, "assembled check failed: " + "; ".join(gate["problems"][:2])
    return ch, None


def load(cid, design, spec, scale=1.0, log=print):
    """spec = (character name, 'production' | 'preview'). Returns a HybridCharacter or None (+ logs why)."""
    from engine2 import library as L
    from engine2.fullpose import FullPoseCharacter
    name, mode = spec[0], spec[1]
    ch = L.Character(name)
    if mode == "production":
        assets, why = ch.render_assets()
        if assets is None:
            log(f"  hybrid '{name}': not used - {why}")
            return None
        files = assets["files"]
        full = cut = None
        poses = {k.split(":", 1)[1]: f for k, f in files.items() if k.startswith("pose:")}
        if poses.get("stand"):
            full = FullPoseCharacter(cid, design, poses, scale)
        if assets["method"] == "cutout":
            cut = _cut_from_parts(cid, design, os.path.join(assets["dir"], "parts"), scale)
        return HybridCharacter(cid, design, cut, full) if (cut or full) else None
    # preview: technically valid candidates, clearly marked
    v = ch.current()
    if not v:
        return None
    data = ch._vdata(v)["assets"]
    ok = {k: os.path.join(ch.dir, v, e["file"]) for k, e in data.items() if e["status"] in (L.REVIEW, L.APPROVED)}
    poses = {k.split(":", 1)[1]: f for k, f in ok.items() if k.startswith("pose:")}
    full = FullPoseCharacter(cid, design, poses, scale) if poses.get("stand") else None
    cut = _cut_from_parts(cid, design, os.path.join(ch.dir, v, "parts"), scale) if "part:head" in ok else None
    if cut is None and "reference" in ok:
        cut, why = _cut_from_reference(cid, design, ok["reference"], scale)
        if cut is None:
            log(f"  hybrid preview '{name}': no cut-out ({why})")
    if cut is None and full is None:
        return None
    return HybridCharacter(cid, design, cut, full, preview=True)
