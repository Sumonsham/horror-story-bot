"""Builds a character's Rigby2D rig from its ORIGINAL reference (asset preparation -> AutoRig -> joints from the
drawing -> animations -> skeleton JSON + atlas for the Python runtime). Needs Node.js 20+ and the Rigby2D source
(git clone https://github.com/jaisurya-dev-art/rigby2d, MIT OR Apache-2.0; no npm packages are needed for these
steps). Output goes to assets/character_rigs/<id>/ (layers, hari.rigby, export/)."""
import json
import os
import shutil
import subprocess
import sys

import cv2

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)


def build(cid, rigby_dir, ref_path=None, out_dir=None, log=print):
    from engine2 import rigprep
    from engine2.rigby import animations
    cfg_f = os.path.join(ROOT, "assets", "character_rigs", cid, "prep.json")
    cfg = json.load(open(cfg_f))
    out = out_dir or os.path.join(ROOT, "assets", "character_rigs", cid)
    os.makedirs(out, exist_ok=True)
    ref = cv2.imread(ref_path or os.path.join(ROOT, cfg["source"]), cv2.IMREAD_UNCHANGED)
    info = rigprep.prepare(ref, cfg, out)
    rigprep.diagnostic(out, ref)
    log(f"  layers: {len(info['order'])}, lost pixels {info['lost_pixels']}")
    node = shutil.which("node") or "node"
    raw = os.path.join(out, f"{cid}_autorig.rigby")
    rig = os.path.join(out, f"{cid}.rigby")
    r = subprocess.run([node, os.path.join(HERE, "layers2rigby.mjs"), rigby_dir, out, raw], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError("AutoRig failed: " + r.stderr[-800:])
    r = subprocess.run([node, os.path.join(HERE, "fixjoints.mjs"), rigby_dir, raw, os.path.join(out, "layers.json"), rig],
                       capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError("joint fix failed: " + r.stderr[-800:])
    fix = json.loads(r.stdout)
    J = {k: (v[0] - info["size"][0] / 2, info["size"][1] - v[1]) for k, v in cfg["joints"].items() if not k.startswith("_")}
    rest = {"hip_r": J["hip_r"], "hip_l": J["hip_l"], "ik_foot_r": J["ankle_r"], "ik_foot_l": J["ankle_l"]}
    ops = animations.all_ops(rest)
    opf = os.path.join(out, "animation_ops.json")
    json.dump(ops, open(opf, "w"))
    cli = os.path.join(rigby_dir, "bin", "rigby.js")
    r = subprocess.run([node, cli, "call", "batch_edit", "--path", rig, "--operations", "@" + opf, "--json"], capture_output=True, text=True)
    if r.returncode:                                       # (older CLIs: the operations inline)
        r = subprocess.run([node, cli, "call", "batch_edit", json.dumps({"path": rig, "operations": ops}), "--json"],
                           capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError("animations failed: " + (r.stdout + r.stderr)[-800:])
    exp = os.path.join(out, "export")
    os.makedirs(exp, exist_ok=True)
    r = subprocess.run([node, cli, "export", rig, "--out", os.path.join(exp, f"{cid}.json"), "--force", "-q"], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError("export failed: " + r.stderr[-800:])
    r = subprocess.run([node, cli, "validate", rig, "--json"], capture_output=True, text=True)
    report = {"layers": info, "joints": fix, "animations": sorted({o["name"] for o in ops if o["op"] == "add_animation"}),
              "validate": r.stdout.strip()[-2000:], "validate_ok": r.returncode == 0}
    json.dump(report, open(os.path.join(out, "rig_report.json"), "w"), indent=1, default=str)
    return report


if __name__ == "__main__":
    print(json.dumps(build(sys.argv[1], sys.argv[2], *(sys.argv[3:4] or [None]), *(sys.argv[4:5] or [None])), default=str)[:3000])
