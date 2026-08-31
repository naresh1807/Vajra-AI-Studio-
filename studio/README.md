# Vajra AI Studio — the desktop IDE (Code-OSS fork)

Per the v3.0 manual, Studio is a **VS Code-class IDE**. Rather than reimplement
the editor shell, Studio is a rebranded fork of **Code-OSS** (the open-source
core of VS Code — the same approach as VSCodium / Cursor / Windsurf) that bundles
the **Vajra extension** (`../vscode-extension/`) as a built-in.

```
studio/
  product.overrides.json     rebrand + telemetry-off values merged into product.json
  marketplace/*.json         Open VSX / Microsoft gallery configs
  scripts/
    bootstrap.ps1            clone Code-OSS @ tag, rebrand, bundle the extension, npm ci
    build.ps1               gulp build -> VajraAIStudio-win32-x64\
    apply-overrides.mjs      idempotent product.json patcher (keeps product.json.orig)
    set-marketplace.mjs      switch the extension gallery
    Directory.Build.targets  native-module build fixups (Spectre off, $(LIB) path)
    _devenv-*.bat            wrap npm ci / gulp in a VS dev environment (vcvars64)
  .builddir                  points at the fork checkout (git-ignored)
  VajraAIStudio-win32-x64/   the built app (git-ignored)
```

**The fork checkout lives outside this repo**, at a **path without spaces**
(default `C:\vajra-studio-build\vscode`) — VS Code's own build scripts break on
spaces in the checkout path. `-BuildDir` overrides it.

## Build

One-time prereqs (admin): **git**, **Node LTS**, **Python 3.12**, and **VS Build
Tools** with the *Desktop development with C++* workload + a Windows 11 SDK.
(The Spectre-mitigated MSVC libs are *not* needed — `bootstrap.ps1` drops that
requirement for the native helper modules via `Directory.Build.targets`.)

```powershell
cd studio
scripts\bootstrap.ps1 -Tag 1.135.0     # clone + rebrand + bundle extension + npm ci  (~20 min)
scripts\build.ps1                      # gulp compile -> VajraAIStudio-win32-x64\  (~25-45 min)
scripts\build.ps1 -Setup               # ...also VajraAIStudioSetup-x64.exe (Inno installer)
scripts\build.ps1 -SkipCompile -Setup  # installer only, from an existing compile
scripts\smoke.ps1                      # headless check: CLI version, rebrand, bundled extension
.\VajraAIStudio-win32-x64\"Vajra AI Studio.exe"
```

The **Core** (the Python `vajra-api`) is started automatically by the bundled
extension when Studio opens (`vajra.autoStartCore`, on by default). Install it
once — `pip install -e ".[dev]"` in the Vajra repo — or point `vajra.coreCommand`
at your own launcher.

**Gotcha:** if `ELECTRON_RUN_AS_NODE` is set in your shell, the `.exe` runs as
plain Node and rejects every flag (`bad option: --user-data-dir`). `Remove-Item
env:ELECTRON_RUN_AS_NODE` first. The `bin\vajra-studio.cmd` CLI is unaffected.

Dev run (no packaging): `cd studio\vscode ; .\scripts\code.bat`

## Extensions & the marketplace

Studio ships with the **Open VSX** gallery (fully open, no Microsoft ToU
strings). To get **GitHub Copilot / Claude Code / ChatGPT / Gemini** — which are
Microsoft-Marketplace-only — switch the gallery:

```powershell
scripts\bootstrap.ps1 -Marketplace ms          # at setup time
node scripts\set-marketplace.mjs ms studio\vscode   # or any time, then rebuild / restart
```

or from inside Studio: **`Vajra: Set Extension Gallery`**. Microsoft's Marketplace
ToU restrict it to Microsoft products and they can rate-limit forks — that's the
same trade-off Cursor / Windsurf make; opt in knowingly.

**Always works regardless of gallery:** *Extensions ▸ … ▸ Install from VSIX…*
(download any `.vsix` from the Marketplace website). And **`Vajra: Install AI
Extensions`** offers a one-click pick list (Copilot, Claude Code, ChatGPT,
Gemini, Continue, Codeium, Cody).

## What's Vajra vs upstream

Everything Vajra-specific lives in **one built-in extension** (`extensions/vajra`),
so upstream stays untouched and rebasing is just:

```powershell
git -C studio\vscode fetch --tags
git -C studio\vscode checkout <newer-tag>
node studio\scripts\apply-overrides.mjs studio\vscode   # re-apply the rebrand
node studio\scripts\patch-fork.mjs     studio\vscode   # re-apply source patches
node studio\scripts\apply-icons.mjs    studio\vscode   # re-apply the icon set
```

`patch-fork.mjs` carries the few upstream source edits `product.overrides.json`
can't express (currently: making the proprietary `@github/copilot` CLI SDK shim
optional — a public `npm ci` only gets a partial package and upstream's
packaging step throws without it). It's idempotent and `build.ps1` re-runs it on
every compile.

## Branding / icon

The app icon (a bolt inside a diamond — *vajra* is both "thunderbolt" and
"diamond") is authored as `branding/vajra.svg`. `apply-icons.mjs` copies the
generated `branding/code.ico` / `.icns` / `.png` set into the fork's
`resources/{win32,darwin,linux,server}` and rebrands the Windows tile manifest —
it has no dependencies and `bootstrap.ps1` / `build.ps1` run it every compile.
After editing the SVG, regenerate the binaries:

```powershell
npm i --no-save sharp png-to-ico
node studio\scripts\regen-icons.mjs      # rewrites branding/*.ico|*.icns|*.png
```

The extension provides: the **Vajra** activity-bar panel (Assisted / Agent /
Computer / OS Dev / Security), right-click + `Ctrl+K` assisted edits with native
diff-apply, inline completions, a native **Test Explorer** (`/api/testing`),
**semantic search** (`/api/rag`), checkpoints, and a status-bar Core indicator —
all talking to the local Python Core.

## Relationship to `studio-desktop/`

`studio-desktop/` (the earlier hand-rolled Tauri + React shell) still builds and
works; it's kept as a lightweight alternative. The Code-OSS fork is the primary
Studio going forward.
