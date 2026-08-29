// Switch the extension gallery in the cloned vscode/product.json.
//   node set-marketplace.mjs <openvsx|ms> [vscodeDir]
import { readFileSync, writeFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const which = (process.argv[2] || "openvsx").toLowerCase();
const vscodeDir = process.argv[3] || join(here, "..", "vscode");
const file = which === "ms" || which === "microsoft" ? "microsoft.json" : "open-vsx.json";

const gallery = JSON.parse(readFileSync(join(here, "..", "marketplace", file), "utf8")).extensionsGallery;
const productPath = join(vscodeDir, "product.json");
const product = JSON.parse(readFileSync(productPath, "utf8"));
product.extensionsGallery = gallery;
// let extensions that are marketplace-only still be trusted for links
product.linkProtectionTrustedDomains = [
  ...(product.linkProtectionTrustedDomains || []),
  "https://marketplace.visualstudio.com",
  "https://open-vsx.org",
];
writeFileSync(productPath, JSON.stringify(product, null, "\t") + "\n");
// remember the choice so build.ps1 can re-apply it after an upstream checkout
writeFileSync(join(vscodeDir, ".vajra-marketplace"), which);
console.log(`extension gallery -> ${which === "ms" || which === "microsoft" ? "Microsoft Marketplace" : "Open VSX"} (${gallery.serviceUrl})`);
