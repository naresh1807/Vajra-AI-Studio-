# Vajra AI — VS Code extension

The Vajra surface for VS Code. Delegates all reasoning and execution to your
**local Vajra Core**; supplies editor context (active file, selection,
workspace). Also the built-in extension bundled by the [Studio fork](../studio/).

## Develop

```powershell
cd vscode-extension
npm install
npm run build        # -> dist/extension.js
```

Press <kbd>F5</kbd> in VS Code for an Extension Development Host.

## Features

| | |
|---|---|
| **Vajra panel** (activity bar) | Assisted (chat) · Agent (autonomous) · Computer · OS Dev · Security — live plan + approval prompts |
| **Assisted edits** | right-click → *Vajra ▸ Explain / Fix / Refactor / Optimize / Write Tests / Document / Security Review*, or <kbd>Ctrl</kbd>+<kbd>K</kbd> for a free-form edit — applied through the native diff editor |
| **Inline completions** | `vajra.inlineCompletions` (off by default — needs a fast local model) |
| **Test Explorer** | native `TestController` backed by `/api/testing` — discover, run, per-test pass/fail |
| **Semantic search** | *Vajra: Semantic Search* → `/api/rag` → quick pick → open at line |
| **Checkpoints** | *Vajra: Create Checkpoint* → `vajra/*` git tag |
| **Status bar** | Core online + primary model |

## Configure

| Setting | Default | |
|---|---|---|
| `vajra.apiUrl` | `http://127.0.0.1:8760` | Local API base URL |
| `vajra.pairingToken` | `change-me-local-only` | must match `VAJRA_PAIRING_TOKEN` |
| `vajra.inlineCompletions` | `false` | keystroke completions from the Core |

## Package

```powershell
npm run package      # -> vajra-ai.vsix
```
