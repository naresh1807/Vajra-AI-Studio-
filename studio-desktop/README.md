# Vajra AI Studio

The AI-native IDE. Tauri + React + **Monaco**. Talks to the local Vajra Core over
`http://127.0.0.1:8760` (`/api/*` + `/ws/events`).

## Layout

```
┌ topbar: project · Core status · Settings ─────────────────────────┐
├ Explorer ┬ editor tabs + Monaco ─────────────┬ Vajra panel ───────┤
│ file     │                                   │ Assisted | Agent   │
│ tree     │                                   │ chat / plan / diff │
│          ├ Terminal | Output ────────────────┤ approvals          │
└──────────┴───────────────────────────────────┴────────────────────┘
```

## Dev

```powershell
cd studio-desktop
npm install
npm run dev          # http://localhost:1420
```

First run: **Settings** → set the pairing token to match `VAJRA_PAIRING_TOKEN` in
the Core's `.env`. Then **Open Folder** (absolute path).

## Modes

- **Manual** — file tree, Monaco tabs, `Ctrl+S` saves via `/api/files/write` (which
  returns a diff + previous content for rollback), integrated terminal.
- **Assisted** — the Vajra panel in chat mode: ask about the open workspace; Vajra
  reads your files (read-only tools) before answering.
- **Agent** — the Vajra panel in agent mode: give a goal, watch the task graph,
  approve gated actions; changed files refresh in the tree when it finishes.

## Full Tauri window / installer

Needs Rust + WebView2 + an icon set (`npx @tauri-apps/cli icon ./app-icon.png`):

```powershell
npm run tauri dev
npm run tauri build        # -> src-tauri/target/release/bundle/
```

## Not yet

LSP diagnostics/autocomplete, DAP debugging, split editor, command palette,
inline completions, Ctrl+K inline edit, diff-editor accept/reject hunks, Git panel
UI. See manual v3.0 §4 / Phases 2-5.
