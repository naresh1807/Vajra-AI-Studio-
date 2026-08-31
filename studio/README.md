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
  branding/                  app icon: vajra.svg master + generated code.{ico,icns,png}
  .builddir                  points at the build dir (git-ignored)
```

**Everything the build produces lives outside this repo**, under the build dir
(default `C:\vajra-studio-build\`): the Code-OSS checkout (`vscode\`), the app
(`VajraAIStudio-win32-x64\`) and the installer (`VajraAIStudioSetup-x64.exe`).
Two reasons it must not be inside the repo: VS Code's build scripts break on
**spaces** in the checkout path, and a 1.3 GB Electron tree under a
**OneDrive-synced** path gets its files dehydrated mid-session — the app then
dies at launch with `Invalid file descriptor to ICU data received`. `-BuildDir`
overrides the location.

## Build

One-time prereqs (admin): **git**, **Node LTS**, **Python 3.12**, and **VS Build
Tools** with the *Desktop development with C++* workload + a Windows 11 SDK.
(The Spectre-mitigated MSVC libs are *not* needed — `bootstrap.ps1` drops that
requirement for the native helper modules via `Directory.Build.targets`.)

```powershell
cd studio
scripts\bootstrap.ps1 -Tag 1.135.0     # clone + rebrand + bundle extension + npm ci  (~20 min)
scripts\build.ps1                      # gulp compile -> <buildDir>\VajraAIStudio-win32-x64\  (~25-45 min)
scripts\build.ps1 -Setup               # ...also <buildDir>\VajraAIStudioSetup-x64.exe (Inno installer)
scripts\build.ps1 -SkipCompile -Setup  # installer only, from an existing compile
scripts\smoke.ps1                      # headless check: CLI version, rebrand, bundled extension
```

The build prints the exact paths when it finishes. The portable app is at
`<buildDir>\VajraAIStudio-win32-x64\` — **double-click `Vajra AI Studio.exe` in
Explorer**, run `Vajra AI Studio.cmd` from a terminal, or run the installer for a
Start-menu entry. Installing is the most reliable: it lands in
`%LOCALAPPDATA%\Programs\` with a shortcut that always launches clean.

The **Core** (the Python `vajra-api`) is started automatically by the bundled
extension when Studio opens (`vajra.autoStartCore`, on by default). Install it
once — `pip install -e ".[dev]"` in the Vajra repo — or point `vajra.coreCommand`
at your own launcher.

**`Invalid file descriptor to ICU data received`** at launch (no window, just
that line) has two causes:

- **OneDrive.** If the app folder is under a synced path, OneDrive dehydrates its
  files and the Electron children can't read `icudtl.dat` in time. Keep the build
  out of OneDrive (the default `C:\vajra-studio-build\` is fine) — or install it.
- **`ELECTRON_RUN_AS_NODE=1`.** VS Code's integrated terminal (and anything an
  extension host spawns) exports it. Launch from Explorer / the Start menu, use
  the generated `Vajra AI Studio.cmd` (it scrubs the var), or
  `Remove-Item env:ELECTRON_RUN_AS_NODE` first. `bin\vajra-studio.cmd` is the CLI
  and *does* want the var set — leave it alone.

An installed copy sidesteps both.

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

`patch-fork.mjs` carries the upstream changes `product.overrides.json` can't
express. Currently: **removes the built-in `extensions/copilot`** (Vajra doesn't
bundle GitHub Copilot; its `@opentelemetry/…` nested `node_modules` also blow
past Windows MAX_PATH, which breaks the Inno installer and recursive deletes),
and makes the leftover Copilot-SDK packaging shim a no-op. Run it **before**
`npm ci` on a fresh checkout so the copilot dir deletes before it grows a deep
`node_modules`; `bootstrap.ps1` and `build.ps1` already sequence it that way.

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
