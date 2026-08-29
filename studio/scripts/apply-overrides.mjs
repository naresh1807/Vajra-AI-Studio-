// Merge studio/product.overrides.json into the cloned vscode/product.json.
// Idempotent: keeps a .orig backup and re-applies from it each run.
import { readFileSync, writeFileSync, existsSync, copyFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const vscodeDir = process.argv[2] || join(here, "..", "vscode");
const productPath = join(vscodeDir, "product.json");
const orig = productPath + ".orig";

if (!existsSync(orig)) copyFileSync(productPath, orig);
const base = JSON.parse(readFileSync(orig, "utf8"));
const overrides = JSON.parse(readFileSync(join(here, "..", "product.overrides.json"), "utf8"));
const merged = { ...base, ...overrides };
writeFileSync(productPath, JSON.stringify(merged, null, "\t") + "\n");
console.log(`product.json: applied ${Object.keys(overrides).length} overrides -> ${merged.nameLong}`);
