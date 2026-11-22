"""Hari's animations, written into the Rigby2D work file as ordinary keys (rigby call batch_edit), so they can be
opened and corrected by hand in the Rigby2D editor (rigby2d.com/editor) and are replayed exactly by its runtimes.

Conventions (Rigby2D): rotations are degrees ADDED to the setup pose, counter-clockwise positive, Y up; the
character faces screen-right, so 'forward' is +x and a forward arm/leg swing is a positive rotation.

ARMS are driven forward-kinematically (shoulder, elbow, wrist keyed like a cut-out animator does); the arm IK
constraints are switched off. LEGS use the IK the rig was built with: the feet are placed (planted) and the knees
bend from the leg lengths - that is what keeps a foot still on the ground.
"""
import math

WALK_T = 1.1          # seconds per cycle (two steps)
STEP = 78.0           # rig px per step (stride/2); the body moves exactly 2*STEP per cycle -> no foot slide
DUTY = 0.60           # part of the cycle a foot is on the ground


def _rot(a, bone, t, v, curve="easeInOut"):
    return {"op": "set_bone_key", "animation": a, "bone": bone, "channel": "rotate", "time": round(t, 4), "value": round(v, 3), "curve": curve}


def _tr(a, bone, t, x, y, curve="linear"):
    return {"op": "set_bone_key", "animation": a, "bone": bone, "channel": "translate", "time": round(t, 4), "x": round(x, 3), "y": round(y, 3), "curve": curve}


def _sc(a, bone, t, x, y, curve="easeInOut"):
    return {"op": "set_bone_key", "animation": a, "bone": bone, "channel": "scale", "time": round(t, 4), "x": round(x, 4), "y": round(y, 4), "curve": curve}


def _foot_track(u):
    """one foot through a walk cycle, u in [0,1): 0 = heel contact in front.
    returns (x offset from under its hip, lift of the ankle, foot rotation)"""
    if u < DUTY:                                        # STANCE: on the ground, moving back at the body's speed
        s = u / DUTY
        x = STEP * (1 - 2 * s)                          # +STEP -> -STEP, linear = planted in the world
        lift = 0.0
        if s < 0.12:                                    # heel strike -> foot flat
            rot = 14.0 * (1 - s / 0.12)
        elif s > 0.78:                                  # heel rises, toe pushes off
            rot = -22.0 * (s - 0.78) / 0.22
            lift = 10.0 * (s - 0.78) / 0.22
        else:
            rot = 0.0
        return x, lift, rot
    s = (u - DUTY) / (1 - DUTY)                         # SWING: forward through the air
    e = 0.5 - 0.5 * math.cos(math.pi * s)
    x = -STEP + 2 * STEP * e
    lift = 10.0 + 34.0 * math.sin(math.pi * min(1.0, s * 1.08))
    lift = max(0.0, lift - 10.0 * s)
    rot = -22.0 + 36.0 * s                              # toe down after push-off -> toe up for the next heel strike
    return x, lift, rot


def walk(rest):
    """six-phase cycle sampled at 24 keys/cycle: contact, down, passing, up, (opposite) contact, down, passing, up.
    rest = setup positions (rig px) of: hip_r, hip_l, ik_foot_r, ik_foot_l (from the rig)."""
    a = "walk"
    ops = [{"op": "add_animation", "name": a, "duration": WALK_T}]
    N = 24
    for k in range(N + 1):
        u = k / N
        t = u * WALK_T
        for side, phase in (("r", 0.0), ("l", 0.5)):
            x, lift, rot = _foot_track((u + phase) % 1.0)
            hx = rest["hip_" + side][0]
            tx, ty = rest["ik_foot_" + side]
            ops.append(_tr(a, "ik_foot_" + side, t, hx + x - tx, lift))
            ops.append(_rot(a, "foot_" + side, t, rot, "linear"))
        # body: lowest just after each contact (weight accepted), highest just after passing
        w = 2 * math.pi * 2 * u
        bob = -12.0 - 5.0 * math.cos(w - 0.55)
        sway = 2.0 * math.sin(2 * math.pi * u)
        ops.append(_tr(a, "hip", t, sway * 0.0, bob))
        ops.append(_rot(a, "hip", t, 1.2 * math.sin(2 * math.pi * u), "linear"))
        ops.append(_rot(a, "chest", t, -2.4 * math.sin(2 * math.pi * u) + 1.5, "linear"))     # slight forward lean
        ops.append(_rot(a, "head", t, 1.6 * math.sin(2 * math.pi * u) - 1.0, "linear"))
        # arms swing opposite to the legs, the forearm lags (follow-through), small wrist drag
        sw = math.sin(2 * math.pi * u + math.pi / 2)    # u=0: right foot in front -> right arm back
        ops.append(_rot(a, "upperarm_r", t, -14.0 * sw - 2.0, "linear"))
        ops.append(_rot(a, "forearm_r", t, 6.0 - 9.0 * math.sin(2 * math.pi * u + math.pi / 2 - 0.5), "linear"))
        ops.append(_rot(a, "hand_r", t, -4.0 * math.sin(2 * math.pi * u + math.pi / 2 - 0.9), "linear"))
        ops.append(_rot(a, "upperarm_l", t, 11.0 * sw + 4.0, "linear"))
        ops.append(_rot(a, "forearm_l", t, 8.0 + 8.0 * math.sin(2 * math.pi * u + math.pi / 2 - 0.5), "linear"))
        ops.append(_rot(a, "hand_l", t, 4.0 * math.sin(2 * math.pi * u + math.pi / 2 - 0.9), "linear"))
    return ops


def idle():
    a, T = "idle", 3.2
    ops = [{"op": "add_animation", "name": a, "duration": T}]
    for t in (0.0, 1.6, 3.2):
        inhale = 1.0 if t == 1.6 else 0.0
        ops.append(_sc(a, "chest", t, 1.0 + 0.012 * inhale, 1.0 + 0.008 * inhale))
        ops.append(_tr(a, "hip", t, 0.0, 1.2 * inhale))
        ops.append(_rot(a, "head", t, 0.8 * inhale - 0.4))
        ops.append(_rot(a, "upperarm_r", t, 1.2 * inhale))
        ops.append(_rot(a, "upperarm_l", t, -1.0 * inhale))
        ops.append(_rot(a, "forearm_r", t, 1.5 * inhale))
        ops.append(_rot(a, "forearm_l", t, 1.5 * inhale))
    return ops


def talk():
    """explaining to someone on his right (screen-right): the far arm comes up, palm open, beats with the words"""
    a, T = "talk", 4.0
    ops = [{"op": "add_animation", "name": a, "duration": T}]
    keys = [(0.0, 0.0, 0.0, 0.0, 0.0), (0.45, 30, 52, 12, -2.0), (0.9, 24, 60, 6, 1.0), (1.35, 34, 48, 14, -2.5),
            (1.9, 27, 58, 8, 1.5), (2.5, 36, 44, 16, -1.5), (3.1, 28, 56, 10, 1.0), (3.6, 12, 25, 4, 0.0), (4.0, 0.0, 0.0, 0.0, 0.0)]
    for t, ua, fa, ha, hd in keys:
        ops.append(_rot(a, "upperarm_l", t, ua))
        ops.append(_rot(a, "forearm_l", t, fa))
        ops.append(_rot(a, "hand_l", t, ha))
        ops.append(_rot(a, "head", t, hd))
        ops.append(_rot(a, "chest", t, -0.8 if ua > 20 else 0.0))
        ops.append(_rot(a, "upperarm_r", t, 3.0 if ua > 20 else 0.0))
        ops.append(_rot(a, "forearm_r", t, 6.0 if ua > 20 else 0.0))
    return ops


def listen():
    """listening (NOT the talking pose): weight back, head tilted toward the speaker, two slow nods, hands still"""
    a, T = "listen", 4.0
    ops = [{"op": "add_animation", "name": a, "duration": T}]
    for t, hd, ch, nod in ((0.0, 0.0, 0.0, 0), (0.6, 4.0, 1.4, 0), (1.2, 4.0, 1.4, 1), (1.45, 4.0, 1.4, 0), (2.4, 4.5, 1.6, 0),
                           (2.9, 4.5, 1.6, 1), (3.15, 4.5, 1.6, 0), (4.0, 0.0, 0.0, 0)):
        ops.append(_rot(a, "head", t, hd - 5.0 * nod))
        ops.append(_rot(a, "chest", t, ch))
        ops.append(_rot(a, "upperarm_l", t, -2.0 * ch / 1.6))
        ops.append(_rot(a, "forearm_l", t, 4.0 * ch / 1.6))
        ops.append(_rot(a, "upperarm_r", t, 2.0 * ch / 1.6))
    return ops


def indicate():
    """'that way' - the far arm stretches out toward screen-right, open hand (there is NO index-finger hand drawing
    yet: a finger-point needs a new hand drawing; this is the open-hand indicating gesture the artwork allows)"""
    a, T = "indicate", 3.0
    ops = [{"op": "add_animation", "name": a, "duration": T}]
    for t, ua, fa, ha, hd, ch in ((0.0, 0, 0, 0, 0, 0), (0.35, 40, 30, 6, 2, -1), (0.6, 62, 6, 14, 3, -2.5), (2.2, 60, 8, 12, 3, -2.5),
                                  (2.7, 20, 20, 4, 1, -1), (3.0, 0, 0, 0, 0, 0)):
        ops.append(_rot(a, "upperarm_l", t, ua))
        ops.append(_rot(a, "forearm_l", t, fa))
        ops.append(_rot(a, "hand_l", t, ha))
        ops.append(_rot(a, "head", t, hd))
        ops.append(_rot(a, "chest", t, ch))
    return ops


def open_palms():
    """both hands open, palms up ('what can I do?') - the drawn open hands, both arms bent at the elbow"""
    a, T = "open_palms", 2.6
    ops = [{"op": "add_animation", "name": a, "duration": T}]
    for t, k in ((0.0, 0.0), (0.45, 1.0), (2.0, 1.0), (2.6, 0.0)):
        ops.append(_rot(a, "upperarm_l", t, 22 * k))
        ops.append(_rot(a, "forearm_l", t, 62 * k))
        ops.append(_rot(a, "hand_l", t, 10 * k))
        ops.append(_rot(a, "upperarm_r", t, 18 * k))
        ops.append(_rot(a, "forearm_r", t, 70 * k))
        ops.append(_rot(a, "hand_r", t, 25 * k))
        ops.append(_rot(a, "head", t, -3 * k))
        ops.append(_tr(a, "hip", t, 0, 3 * k, "easeInOut"))
    return ops


def sit(rest, seat_drop=112.0, back=-30.0, feet_fwd=44.0):
    """sitting down on a seat (the scene must draw the seat - the QA checks it): hips go down and back onto the seat,
    the IK feet stay planted a little forward, knees bend forward; then a seated talking loop 'sit_talk'"""
    ops = [{"op": "add_animation", "name": "sit_down", "duration": 1.4}, {"op": "add_animation", "name": "sit_talk", "duration": 4.0}]
    for t, k in ((0.0, 0.0), (0.35, 0.25), (0.9, 0.85), (1.4, 1.0)):
        e = k
        ops.append(_tr("sit_down", "hip", t, back * e, -seat_drop * e, "easeInOut"))
        ops.append(_rot("sit_down", "chest", t, -9.0 * math.sin(math.pi * e) + 2.0 * e))   # leans forward to sit
        ops.append(_rot("sit_down", "head", t, 5.0 * math.sin(math.pi * e)))
        for sd in ("r", "l"):
            ops.append(_tr("sit_down", "ik_foot_" + sd, t, feet_fwd * e, 0.0, "easeInOut"))
        ops.append(_rot("sit_down", "upperarm_r", t, 14 * e))
        ops.append(_rot("sit_down", "forearm_r", t, 52 * e))
        ops.append(_rot("sit_down", "hand_r", t, 20 * e))
        ops.append(_rot("sit_down", "upperarm_l", t, 4 * e))
        ops.append(_rot("sit_down", "forearm_l", t, 38 * e))
    for t, ua, fa, hd in ((0.0, 4, 38, 0), (0.6, 26, 60, -2), (1.3, 20, 66, 1), (2.0, 30, 54, -2), (2.8, 22, 62, 1), (4.0, 4, 38, 0)):
        ops.append(_tr("sit_talk", "hip", t, back, -seat_drop, "linear"))
        ops.append(_rot("sit_talk", "chest", t, 2.0))
        for sd in ("r", "l"):
            ops.append(_tr("sit_talk", "ik_foot_" + sd, t, feet_fwd, 0.0, "linear"))
        ops.append(_rot("sit_talk", "upperarm_r", t, 14))
        ops.append(_rot("sit_talk", "forearm_r", t, 52))
        ops.append(_rot("sit_talk", "hand_r", t, 20))
        ops.append(_rot("sit_talk", "upperarm_l", t, ua))
        ops.append(_rot("sit_talk", "forearm_l", t, fa))
        ops.append(_rot("sit_talk", "hand_l", t, 8))
        ops.append(_rot("sit_talk", "head", t, hd))
    return ops


def all_ops(rest):
    ops = [{"op": "set_constraint", "constraint": "ik_hand_r", "settings": {"mix": 0}},
           {"op": "set_constraint", "constraint": "ik_hand_l", "settings": {"mix": 0}}]
    for f in (idle(), talk(), listen(), indicate(), open_palms(), walk(rest), sit(rest)):
        ops += f
    return ops
