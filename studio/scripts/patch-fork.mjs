// Source patches applied to the cloned Code-OSS fork (things product.overrides.json
// can't express). Idempotent: safe to re-run, and re-applied by build.ps1 on every
// compile so an upstream checkout doesn't silently drop them.
//
//   node scripts/patch-fork.mjs <vscodeDir>
import { readFileSync, writeFileSync, existsSync, rmSync } from "node:fs";
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

// --- 1. Drop the proprietary built-in `copilot` extension -------------------
// Vajra ships its own AI via the bundled `vajra` extension and does not bundle
// GitHub Copilot. Removing extensions/copilot before `npm ci`:
//   * skips fetching its ~1150-package dependency tree (faster, ~250 MB smaller)
//   * kills the @opentelemetry/... nested-node_modules paths that blow past
//     Windows MAX_PATH - which broke the Inno installer (MoveFile code 3) and
//     Remove-Item on the build tree.
// Runs before npm ci in bootstrap.ps1, so the dir has no node_modules yet and
// deletes cheaply. packageCopilotExtensionStream() already no-ops on a missing
// dir; the shim patch below covers the packaging task.
{
  const copilotDir = join(vscodeDir, "extensions", "copilot");
  if (existsSync(copilotDir)) {
    try {
      rmSync(copilotDir, { recursive: true, force: true, maxRetries: 3 });
      console.log("patch-fork: removed extensions/copilot");
      applied++;
    } catch (err) {
      console.warn(`patch-fork: could not remove extensions/copilot (${err.code || err.message}) - ` +
        "the shim patch still lets the build finish, but the Inno installer may hit MAX_PATH");
    }
  }
}

// --- 2. Copilot CLI SDK shim is optional for this fork ----------------------
// Belt-and-suspenders for the removal above: VS Code's packaging still runs
// prepareBuiltInCopilotRipgrepShim, which hard-throws when the proprietary
// @github/copilot CLI SDK isn't fully present. Degrade it to a no-op.
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
