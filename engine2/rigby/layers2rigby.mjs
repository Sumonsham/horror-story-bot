// SPDX-License-Identifier: MIT
// Prepared layers (full-canvas transparent PNGs, layers.json from engine2/rigprep.py) -> an UNRIGGED Rigby2D work file
// (.rigby), exactly as Rigby2D's own "Import PSD" lays them out (canvas bottom-centre = origin, Y up), then Rigby2D's
// AutoRig (bones, weighted bending meshes, IK) - the editor's own code, run from the Rigby2D source folder.
// usage: node layers2rigby.mjs <rigby2d source dir> <layers dir> <out.rigby> [roles.json]
import fs from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const [, , RIGBY, DIR, OUT, ROLES] = process.argv;
const imp = (p) => import(pathToFileURL(path.join(RIGBY, p)).href);
const { makeAttachment, makeSlot, Skeleton } = await imp('src/core/model.js');
const { transform } = await imp('src/core/math.js');
const { autoRig } = await imp('src/core/autorig.js');
const { decodePng, encodePng, alphaOf } = await imp('src/mcp/png.js');
const { save } = await imp('src/mcp/edits.js');

const info = JSON.parse(await fs.readFile(path.join(DIR, 'layers.json'), 'utf8'));
const [CW, CH] = info.size;
const doc = new Skeleton();
doc.name = info.character || 'character';
const entries = new Map();
const pixels = new Map();
for (const name of info.order) {
  const full = decodePng(await fs.readFile(path.join(DIR, info.layers[name].file)));
  const [x0, y0, x1, y1] = info.layers[name].bbox;
  const w = x1 - x0 + 1, h = y1 - y0 + 1;
  const data = new Uint8Array(w * h * 4);
  for (let y = 0; y < h; y++) data.set(full.data.subarray(((y + y0) * CW + x0) * 4, ((y + y0) * CW + x0 + w) * 4), y * w * 4);
  const rgba = { width: w, height: h, data };
  pixels.set(name, rgba);
  entries.set(`images/${name}.png`, encodePng(rgba));
  doc.images.push({ name, path: null, width: w, height: h });
  const att = makeAttachment(name, name, transform((x0 + x1 + 1) / 2 - CW / 2, CH - (y0 + y1 + 1) / 2, 0), w, h);
  doc.slots.push(makeSlot(doc.uniqueSlotName(name), 0, att));
}
const args = ROLES ? JSON.parse(await fs.readFile(ROLES, 'utf8')) : {};
const report = autoRig(doc, (n) => (pixels.has(n) ? alphaOf(pixels.get(n)) : null), { meshes: 'deforming', ik: true, ...args });
await fs.rm(OUT, { force: true });
const file = await save({}, { file: path.resolve(OUT), format: 'rigby', doc, entries }, {});
console.log(JSON.stringify({ file, report }, null, 1));
