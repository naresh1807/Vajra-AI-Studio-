// Regenerate the binary icon assets in studio/branding/ from vajra.svg.
// DEV-ONLY: needs `sharp` and `png-to-ico` (not repo deps). Run after editing
// the master SVG, then commit the results. The build itself only runs
// apply-icons.mjs, which just copies these pre-generated files.
//
//   npm i --no-save sharp png-to-ico && node studio/scripts/regen-icons.mjs
import sharp from "sharp";
import pngToIco from "png-to-ico";
import { readFileSync, writeFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const brand = join(here, "..", "branding");
const master = readFileSync(join(brand, "vajra.svg"));
const out = (name) => join(brand, name);

const png = (svg, size) => sharp(svg, { density: 512 }).resize(size, size).png({ compressionLevel: 9 }).toBuffer();

// --- PNGs -------------------------------------------------------------------
const pngSizes = [16, 20, 24, 32, 40, 48, 64, 70, 128, 150, 192, 150 * 2, 256, 512, 1024];
const cache = new Map();
for (const s of [...new Set(pngSizes)]) cache.set(s, await png(master, s));

writeFileSync(out("code-1024.png"), cache.get(1024));           // linux / server (VS Code ships 1024 everywhere)
writeFileSync(out("code-512.png"), cache.get(512));
writeFileSync(out("code-192.png"), cache.get(192));
writeFileSync(out("code_70x70.png"), cache.get(70));            // win small tile
writeFileSync(out("code_150x150.png"), cache.get(150));        // win medium tile
writeFileSync(out("icon-256.png"), cache.get(256));            // vscode-extension marketplace icon

// --- ICO (Windows app + file assoc) ---------------------------------------
const icoSizes = [16, 20, 24, 32, 40, 48, 64, 128, 256];
writeFileSync(out("code.ico"), await pngToIco(icoSizes.map((s) => cache.get(s))));
writeFileSync(out("favicon.ico"), await pngToIco([16, 24, 32, 48].map((s) => cache.get(s))));

// --- ICNS (macOS) --------------------------------------------------------
// Minimal modern icns: PNG payloads under the ic07..ic14 OSTypes.
const icnsParts = [
  ["ic07", 128], ["ic08", 256], ["ic09", 512], ["ic10", 1024],
  ["ic11", 32], ["ic12", 64], ["ic13", 256], ["ic14", 512],
];
const chunks = [];
for (const [type, size] of icnsParts) {
  const data = cache.get(size);
  const head = Buffer.alloc(8);
  head.write(type, 0, "ascii");
  head.writeUInt32BE(data.length + 8, 4);
  chunks.push(head, data);
}
const body = Buffer.concat(chunks);
const icnsHead = Buffer.alloc(8);
icnsHead.write("icns", 0, "ascii");
icnsHead.writeUInt32BE(body.length + 8, 4);
writeFileSync(out("code.icns"), Buffer.concat([icnsHead, body]));

console.log("regen-icons: wrote code.ico, favicon.ico, code.icns, code-{1024,512,192}.png, code_{70x70,150x150}.png, icon-256.png");
