# Windows installer

The Windows installer is produced by Tauri from `studio-desktop/`.

## Build

```powershell
pwsh -File scripts/build-installer.ps1
# or, by hand:
cd studio-desktop
npm install
npm run tauri build
```

Output:

```
studio-desktop/src-tauri/target/release/bundle/nsis/Vajra AI Studio_0.2.0_x64-setup.exe
```

(a ~5 MB NSIS installer; the packaged app is ~14 MB). Build artifacts are not
committed — `target/` is gitignored.

## Prerequisites

- Rust (`rustup`, `x86_64-pc-windows-msvc` toolchain — the default)
- **Visual Studio Build Tools** with the "Desktop development with C++" workload
  (MSVC compiler + linker + Windows SDK). Without it the Rust link step fails.
- WebView2 runtime — preinstalled on Windows 10/11.

NSIS itself is downloaded automatically by Tauri on first build.

## What the installer contains

- `vajra-studio.exe` — the desktop shell (Tauri + WebView2, ~14 MB)
- The bundled Studio UI (Monaco, all panels)

It does **not** bundle the Python Vajra Core. After installing, run
`pip install -e .` in the repo so `vajra-api` is on PATH; the Studio can then
start/stop it as a sidecar (`start_core` / `stop_core`), or run it yourself.

## Rename for distribution

The manual calls the deliverable `VajraAI-Setup.exe`:

```powershell
Copy-Item "studio-desktop/src-tauri/target/release/bundle/nsis/Vajra AI Studio_0.2.0_x64-setup.exe" `
          "VajraAI-Setup.exe"
```
