// Source patches applied to the cloned Code-OSS fork (things product.overrides.json
// can't express). Idempotent: safe to re-run, and re-applied by build.ps1 on every
// compile so an upstream checkout doesn't silently drop them.
//
//   node scripts/patch-fork.mjs <vscodeDir>
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const vscodeDir = process.argv[2] || join(here, "..", "vscode");

let applied = 0;
const patch = (relPath, edits) => {
  const p = join(vscodeDir, relPath);
  if (!existsSync(p)) {
    console.warn(`patch-fork: ${relPath} not found - skipped`);
    return;
  }
  let txt = readFileSync(p, "utf8");
  const before = txt;
  for (const [find, replace, tag] of edits) {
    if (txt.includes(replace)) continue; // already patched
    if (!txt.includes(find)) {
      console.warn(`patch-fork: anchor for "${tag}" not found in ${relPath} (upstream changed?) - skipped`);
      continue;
    }
    txt = txt.replace(find, replace);
    console.log(`patch-fork: ${relPath} <- ${tag}`);
    applied++;
  }
  if (txt !== before) writeFileSync(p, txt);
};

// --- 1. Copilot CLI SDK shim is optional for this fork -----------------------
// VS Code's packaging hard-requires the proprietary @github/copilot CLI SDK
// (Microsoft restores it from an authenticated pre-built VSIX). A public
// `npm ci` only yields a partial package, so `prepareBuiltInCopilotRipgrepShim`
// throws and fails the whole build. Vajra ships its own AI via the bundled
// `vajra` extension and does not bundle Copilot - degrade the shim to a no-op
// when its inputs are absent.
patch("build/lib/copilot.ts", [
  [
    "\t\tthrow new Error(`[prepareBuiltInCopilotRipgrepShim] Copilot SDK directory not found at ${copilotSdkBase}`);",
    "\t\tconsole.warn(`[prepareBuiltInCopilotRipgrepShim] Copilot SDK not present at ${copilotSdkBase} - skipping shim (vajra fork).`);\n\t\treturn;",
    "copilot: optional SDK",
  ],
  [
    "\t\tthrow new Error(`[prepareBuiltInCopilotRipgrepShim] ripgrep source not found at ${ripgrepSource} (build platform=${platform}, arch=${arch}, computed platformArch=${platformArch}). ${diagnostics}`);",
    "\t\tconsole.warn(`[prepareBuiltInCopilotRipgrepShim] ripgrep source not found at ${ripgrepSource} - skipping shim (vajra fork). ${diagnostics}`);\n\t\treturn;",
    "copilot: optional ripgrep",
  ],
]);

console.log(applied ? `patch-fork: ${applied} edit(s) applied.` : "patch-fork: nothing to do (already patched).");
