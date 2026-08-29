# Vajra AI Studio

The AI-native IDE. Tauri + React + **Monaco**. Talks to the local Vajra Core over
`http://127.0.0.1:8760` (`/api/*` + `/ws/events`).

## Layout

```
┌ topbar: project · ▷ Debug · Core status · Settings ───────────────────┐
├ Explorer|Search|SCM ┬ editor tabs + Monaco ────────┬ Vajra panel ─────┤
│ file tree           │  LSP diagnostics/complete    │ Assisted | Agent │
│ or search hits      │  breakpoints · inline AI     │ | Computer       │
│ or git changes      ├ Terminal|Output|Services|Debug┤ plan · approvals │
└─────────────────────┴──────────────────────────────┴──────────────────┘
```

## Dev (browser UI)

```powershell
cd studio-desktop
npm install
npm run dev          # http://localhost:1420
```

First run: **Settings** → set the pairing token to match `VAJRA_PAIRING_TOKEN`
in the Core's `.env`. Then **Open Folder**.

## Native window + installer

```powershell
npm run tauri dev            # native window (hot-reload)
npm run tauri build          # -> src-tauri/target/release/bundle/nsis/*-setup.exe
```

Needs Rust (`rustup`) and WebView2 (preinstalled on Win10/11). Icons are
committed under `src-tauri/icons/`; regenerate from a 1024px PNG with
`npx @tauri-apps/cli icon ./app-icon.png`.

The packaged app can start/stop the local Vajra Core (`vajra-api`) as a sidecar
(`start_core` / `stop_core` Tauri commands) — install the Python package with
`pip install -e .` so `vajra-api` is on PATH.

## Editor features

Manual · Assisted · Agent · Computer modes · LSP (diagnostics, completion,
hover, go-to-definition for Python/TS/JS) · inline AI completions (opt-in) ·
DAP debugging (breakpoints, step, variables, console) · Format Document
(ruff / prettier, Shift+Alt+F) · Git panel (stage/commit/checkpoint/restore) ·
command palette (Ctrl+Shift+P) · quick-open (Ctrl+P) · project search
(Ctrl+Shift+F) · integrated terminal · dev-server management (Services tab).

## Not yet

Split editor, minimap toggle UI, extension manager. See manual v3.0 §4.
