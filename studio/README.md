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
scripts\bootstrap.ps1 -Tag 1.135.0     # pick the latest stable tag from github.com/microsoft/vscode/tags
scripts\build.ps1                      # ~30-45 min first time
.\VajraAIStudio-win32-x64\VajraAIStudio.exe
```

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
studio\scripts\apply-overrides.mjs studio\vscode   # re-apply the rebrand
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
