// SPDX-License-Identifier: MIT
// Puts the joints AutoRig guessed onto the joints read off the drawing (prep.json "joints"), with Rigby2D's own
// "Bone only" setup edit (setBoneSetupOnly): the artwork and the weighted mesh vertices stay exactly where they are
// drawn, only the pivots move. IK is set aside while the joints move, then put back with each target on its joint.
// usage: node fixjoints.mjs <rigby2d dir> <in.rigby> <layers.json> <out.rigby>
import fs from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const [, , RIGBY, IN, INFO, OUT] = process.argv;
const imp = (p) => import(pathToFileURL(path.join(RIGBY, p)).href);
const { loadProject } = await imp('src/mcp/tools.js');
const { save } = await imp('src/mcp/edits.js');
const { setBoneSetupOnly, setupWorld } = await imp('src/editor/setupmove.js');
const { Pose } = await imp('src/core/pose.js');
const { paintWeights } = await imp('src/core/meshgeom.js');

const info = JSON.parse(await fs.readFile(INFO, 'utf8'));
const [CW, CH] = info.size;
const J = {};
for (const [k, v] of Object.entries(info.joints)) if (!k.startsWith('_')) J[k] = [v[0] - CW / 2, CH - v[1]];   // image -> rig space
const p = await loadProject(path.resolve(IN));
const doc = p.doc;
const idx = (n) => doc.bones.findIndex((b) => b.name === n);
// bone: [head joint, tip joint]
const PLAN = [
  ['neck', 'neck', 'head'], ['head', 'head', null],
  ['upperarm_r', 'shoulder_r', 'elbow_r'], ['forearm_r', 'elbow_r', 'wrist_r'], ['hand_r', 'wrist_r', null],
  ['upperarm_l', 'shoulder_l', 'elbow_l'], ['forearm_l', 'elbow_l', 'wrist_l'], ['hand_l', 'wrist_l', null],
  ['thigh_r', 'hip_r', 'knee_r'], ['shin_r', 'knee_r', 'ankle_r'], ['foot_r', 'ankle_r', 'toe_r'],
  ['thigh_l', 'hip_l', 'knee_l'], ['shin_l', 'knee_l', 'ankle_l'], ['foot_l', 'ankle_l', 'toe_l'],
];
const ik = doc.ik;
doc.ik = [];
const log = [];
for (const [bn, h, t] of PLAN) {
  const i = idx(bn);
  if (i < 0 || !J[h]) continue;
  const W = setupWorld(doc);
  const par = doc.bones[i].parent;
  const P = W[par];
  const [lx, ly] = P.inverse().apply(J[h]);
  const setup = { ...doc.bones[i].setup, x: lx, y: ly };
  if (t && J[t]) {
    const ang = (Math.atan2(J[t][1] - J[h][1], J[t][0] - J[h][0]) * 180) / Math.PI;
    setup.rotation = ang - P.rotation();
    doc.bones[i].length = Math.hypot(J[t][0] - J[h][0], J[t][1] - J[h][1]);
  } else if (bn === 'head') {
    setup.rotation = 90 - P.rotation();
  }
  setBoneSetupOnly(doc, i, setup);
  const w = setupWorld(doc)[i];
  log.push({ bone: bn, want: J[h].map((v) => +v.toFixed(1)), got: [+w.tx.toFixed(1), +w.ty.toFixed(1)] });
}
doc.ik = ik;
// IK targets onto the joints (targets hang from the root, so local = rig space)
const W = setupWorld(doc);
for (const c of doc.ik) {
  const end = c.bones[c.bones.length - 1];
  const tgt = doc.bones[c.target];
  const tipBone = doc.bones.findIndex((b) => b.parent === end && !b.name.startsWith('ik_'));
  const at = tipBone >= 0 ? [W[tipBone].tx, W[tipBone].ty] : W[end].apply([doc.bones[end].length, 0]);
  const pw = tgt.parent === null ? null : W[tgt.parent];
  const [x, y] = pw ? pw.inverse().apply(at) : at;
  tgt.setup = { ...tgt.setup, x, y };
}
// weight painting (prep.json "weights": [bone, joint, radius px, strength]) with Rigby2D's own brush
const PAINT = info.weights || {};
{
  const W = setupWorld(doc);
  for (const slot of doc.slots) {
    for (const att of slot.attachments ?? []) {
      const plan = PAINT[att.name];
      if (!plan || att.type !== 'mesh' || !att.weights) continue;
      const pts = att.weights.map((list) => list.reduce((acc, w) => { const q = W[w.bone].apply([w.x, w.y]); return [acc[0] + q[0] * w.weight, acc[1] + q[1] * w.weight]; }, [0, 0]));
      const ws = att.weights.map((list) => list.map((w) => ({ bone: w.bone, weight: w.weight })));
      for (const [bn, jn, radius, strength] of plan) {
        const b = idx(bn);
        if (b < 0 || !J[jn]) continue;
        const changed = paintWeights(pts, ws, b, J[jn], radius, strength);
        log.push({ paint: att.name, bone: bn, vertices: changed.length });
      }
      att.weights = ws.map((list, i) => list.map((w) => { const [x, y] = W[w.bone].inverse().apply(pts[i]); return { bone: w.bone, x, y, weight: w.weight }; }));
    }
  }
}
// each chain bends the way the drawing does (a knee forward, an elbow as drawn): of the two IK solutions, the one
// that puts the middle joint where it is drawn
const MID = { ik_hand_r: 'elbow_r', ik_hand_l: 'elbow_l', ik_foot_r: 'knee_r', ik_foot_l: 'knee_l' };
for (const c of doc.ik) {
  const j = J[MID[c.name]];
  if (!j) continue;
  const mid = c.bones[c.bones.length - 1];
  const e = (bp) => { c.bendPositive = bp; const w = new Pose(doc).world[mid]; return Math.hypot(w.tx - j[0], w.ty - j[1]); };
  const a = e(true), b = e(false);
  c.bendPositive = a <= b;
  log.push({ ik: c.name, bendPositive: c.bendPositive, middle_joint_error_px: +Math.min(a, b).toFixed(2) });
}
const err = doc.validate();
if (err) throw new Error(err);
await fs.rm(OUT, { force: true });
p.file = path.resolve(OUT);
await save({}, p, {});
console.log(JSON.stringify(log));
