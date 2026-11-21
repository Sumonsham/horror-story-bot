"""MOTION ASSISTANT (assistant 5) - role: every movement must look like a real person's, never robotic.

It reads the finished plan (before anything is drawn) and checks + FIXES:
  - walking / running speed: a real person's (walk ~1.3 m/s, run ~3 m/s) - no slow motion, no gliding
  - nobody walks or runs while still sitting: he stands up first (1.4 s, leaning forward as people do)
  - a turn takes at least 0.5 s (head first, then shoulders, then feet - done by the renderer)
  - standing up / sitting down takes 1.2-1.8 s, never a jump between poses
  - two people never stand inside each other (except a hug / a handshake, which have exact distances:
    a handshake 200 px apart so the two hands really meet, a hug 70 px apart so the arms go round)
  - a ghost may float and pass close - it is not a person
And the renderer adds the life a real body has (what this assistant asks of it):
  ease-in / ease-out of every walk (no robot start or stop), the feet planted (the step length follows the
  distance), a small body bob and counter-sway in walking, the head leads a turn, the hands relax, breathing,
  a slow weight shift while standing, blinks, listeners nod, speakers gesture.
Returns a Bengali report: what was checked, what was fixed.
"""
from animation_renderer import RUN_SPEED, WALK_SPEED


def check_and_fix(plan):
    rep = {"checked": 0, "fixed": [], "ok": []}
    chars = {c["id"]: c for c in plan.get("characters", [])}
    acts = plan.get("actions", [])
    ghost = {cid for cid, c in chars.items() if isinstance(c.get("design"), dict) and c["design"].get("ghost")}
    # 1) walking / running speed
    for a in acts:
        if a["type"] in ("walk", "run"):
            rep["checked"] += 1
            x0 = _x_before(plan, a)
            dist = abs(a["to_x"] - x0)
            dur = max(0.01, a["t1"] - a["t0"])
            v = dist / dur
            real = (RUN_SPEED if a["type"] == "run" else WALK_SPEED) * chars.get(a["who"], {}).get("scale", 1.0)
            if dist > 5 and not (0.75 * real <= v <= 1.35 * real):
                a["t1"] = round(a["t0"] + dist / real, 2)
                rep["fixed"].append(f"{a['who']}: {'হাঁটা' if a['type'] == 'walk' else 'দৌড়'}-র গতি {v:.0f} থেকে "
                                    f"স্বাভাবিক {real:.0f} px/s করা হল")
    # 2) never walk while sitting: stand up first
    for a in sorted([a for a in acts if a["type"] in ("walk", "run")], key=lambda a: a["t0"]):
        c = chars.get(a["who"])
        if not c or c.get("start_pose", "stand") != "sit" or a["who"] in ghost:
            continue
        ups = [u for u in acts if u["who"] == a["who"] and u["type"] == "stand_up" and u["t0"] <= a["t0"]]
        if not ups:
            st = {"t0": round(max(0.0, a["t0"] - 1.5), 2), "t1": round(max(0.0, a["t0"] - 1.5) + 1.4, 2), "who": a["who"], "type": "stand_up"}
            acts.append(st)
            if st["t1"] > a["t0"]:
                sh = st["t1"] - a["t0"] + 0.05
                a["t0"] += sh
                a["t1"] += sh
            rep["fixed"].append(f"{a['who']}: বসে থেকেই হাঁটছিল - আগে উঠে দাঁড়ানো যোগ হল")
    # 2b) never flip round on the spot: turn first (head, shoulders, then feet), then walk
    for a in sorted([a for a in acts if a["type"] in ("walk", "run")], key=lambda a: a["t0"]):
        if a["who"] in ghost:
            continue
        x0 = _x_before(plan, a)
        if abs(a["to_x"] - x0) < 5:
            continue
        want = 1.0 if a["to_x"] > x0 else -1.0
        have = _facing_at(plan, a["who"], a["t0"] - 0.01)
        if have * want < 0 and not any(b["who"] == a["who"] and b["type"] == "turn" and abs(b["t1"] - a["t0"]) < 0.3 for b in acts):
            acts.append({"t0": round(a["t0"], 2), "t1": round(a["t0"] + 0.65, 2), "who": a["who"], "type": "turn", "to": want})
            a["t0"] = round(a["t0"] + 0.6, 2)
            a["t1"] = round(a["t1"] + 0.6, 2)
            rep["fixed"].append(f"{a['who']}: উল্টো দিকে হাঁটার আগে ঘুরে দাঁড়ানো যোগ হল (মাথা আগে, তারপর শরীর)")
    # 3) minimum durations: no snapping between poses
    for a in acts:
        need = {"turn": 0.5, "look": 0.45, "look_back": 0.6, "stand_up": 1.2, "sit_down": 1.2, "appear": 1.0, "vanish": 1.0}.get(a["type"])
        if need:
            rep["checked"] += 1
            if a["t1"] - a["t0"] < need:
                a["t1"] = round(a["t0"] + need, 2)
                rep["fixed"].append(f"{a['who']}: '{a['type']}' খুব তাড়াতাড়ি ছিল - {need} সেকেন্ড করা হল")
    # 4) people never stand inside each other
    ids = [c for c in chars if c not in ghost]
    close_ok = {(a["who"], a.get("partner")) for a in acts if a["type"] in ("hug", "handshake")}
    for i, p in enumerate(ids):
        for q in ids[i + 1:]:
            rep["checked"] += 1
            if (p, q) in close_ok or (q, p) in close_ok:
                continue
            if abs(chars[p]["x"] - chars[q]["x"]) < 150 and not chars[p].get("t_in") and not chars[q].get("t_in"):
                move = (150 - abs(chars[p]["x"] - chars[q]["x"])) / 2 + 1
                sgn = 1 if chars[q]["x"] >= chars[p]["x"] else -1
                chars[p]["x"] -= sgn * move
                chars[q]["x"] += sgn * move
                rep["fixed"].append(f"{p} আর {q} একে অপরের গায়ে দাঁড়িয়ে ছিল - সরিয়ে দেওয়া হল")
    # 5) handshake / hug distances (the hands must really meet)
    for a in acts:
        if a["type"] in ("handshake", "hug") and a.get("partner") in chars:
            rep["checked"] += 1
            want = 200.0 if a["type"] == "handshake" else 70.0
            xa, xb = _x_at(plan, a["who"], a["t0"]), _x_at(plan, a["partner"], a["t0"])
            if abs(abs(xa - xb) - want) > 25:
                rep["fixed"].append(f"{a['who']}–{a['partner']}: {a['type']}-এর দূরত্ব {abs(xa - xb):.0f}px (চাই {want:.0f}) - "
                                    "পরিকল্পনায় হাঁটা যোগ করা দরকার")
            else:
                rep["ok"].append(f"{a['type']}: দূরত্ব ঠিক ({abs(xa - xb):.0f}px)")
    plan["actions"] = acts
    rep["summary_bn"] = (f"চলাফেরা-সহকারী: {rep['checked']}টা নড়াচড়া দেখেছে, {len(rep['fixed'])}টা ঠিক করেছে"
                         + (f" ({'; '.join(rep['fixed'][:3])})" if rep["fixed"] else " - সব স্বাভাবিক"))
    return rep


def _x_before(plan, a):
    """where a character stands when this walk begins (after its earlier walks)"""
    c = next(c for c in plan["characters"] if c["id"] == a["who"])
    x = c["x"]
    for b in sorted((b for b in plan["actions"] if b["who"] == a["who"] and b["type"] in ("walk", "run") and b["t0"] < a["t0"]),
                    key=lambda b: b["t0"]):
        x = b["to_x"]
    return x


def _x_at(plan, who, t):
    c = next(c for c in plan["characters"] if c["id"] == who)
    x = c["x"]
    for b in sorted((b for b in plan["actions"] if b["who"] == who and b["type"] in ("walk", "run") and b["t0"] < t),
                    key=lambda b: b["t0"]):
        x = b["to_x"] if t >= b["t1"] else x + (b["to_x"] - x) * (t - b["t0"]) / max(0.01, b["t1"] - b["t0"])
    return x


def _facing_at(plan, who, t):
    c = next(c for c in plan["characters"] if c["id"] == who)
    f = c.get("facing", 1.0)
    for b in sorted((b for b in plan["actions"] if b["who"] == who and b["t0"] <= t), key=lambda b: b["t0"]):
        if b["type"] == "turn":
            f = b["to"]
        elif b["type"] in ("walk", "run"):
            x0 = _x_before(plan, b)
            if t >= b["t1"] and b.get("face") is not None:
                f = b["face"]
            elif abs(b["to_x"] - x0) > 5:
                f = 1.0 if b["to_x"] > x0 else -1.0
    return f
