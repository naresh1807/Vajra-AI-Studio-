# Vajra AI — Desktop App

Primary execution host. React + Vite UI, packaged as a Windows app with Tauri 2.
It can start/stop the local Vajra Core (`vajra-api`) as a sidecar.

## Dev (browser UI only)

```powershell
cd studio-desktop
npm install
npm run dev        # http://localhost:1420 — talks to Vajra Core on :8760
```

## Dev (full Tauri window)

Needs Rust (`rustup`), WebView2 (preinstalled on Win10/11) and an icon set:

```powershell
npx @tauri-apps/cli icon ./app-icon.png    # generates src-tauri/icons/*
npm run tauri dev
```

## Build installer

```powershell
npm run tauri build        # -> src-tauri/target/release/bundle/{msi,nsis}/
```

Rename the artifact to `VajraAI-Setup.exe` / `VajraAI.msi` for distribution.

## Screens

Dashboard · Chat / Goal · Projects · Task Graph · Approvals · Logs · Settings
(VS Code Coordinator, Terminal, Diff Review and Memory screens land in later phases.)
