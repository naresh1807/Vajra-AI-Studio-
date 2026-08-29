# Vajra AI Studio — the desktop IDE (Code-OSS fork)

Per the v3.0 manual, Studio is a **VS Code-class IDE**. Rather than reimplement
the editor shell, Studio is a rebranded fork of **Code-OSS** (the open-source
core of VS Code — the same approach as VSCodium / Cursor / Windsurf) that bundles
the **Vajra extension** (`../vscode-extension/`) as a built-in.

```
studio/
  product.overrides.json     rebrand + telemetry-off values merged into product.json
  scripts/
    bootstrap.ps1            clone Code-OSS @ tag, rebrand, bundle the extension, npm ci
    build.ps1               gulp build -> VajraAIStudio-win32-x64\
    apply-overrides.mjs      idempotent product.json patcher (keeps product.json.orig)
  vscode/                    the fork (git-ignored; created by bootstrap.ps1)
  VajraAIStudio-win32-x64/   the built app (git-ignored)
```

## Build

```powershell
cd studio
scripts\bootstrap.ps1 -Tag 1.135.0     # pick the latest stable tag from github.com/microsoft/vscode/tags
scripts\build.ps1                      # ~30-45 min first time
.\VajraAIStudio-win32-x64\VajraAIStudio.exe
```

Dev run (no packaging): `cd studio\vscode ; .\scripts\code.bat`

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
