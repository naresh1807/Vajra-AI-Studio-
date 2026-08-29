# Vajra AI — VS Code extension

The primary engineering surface for Vajra AI. Supplies editor context (active file,
selection, workspace, diagnostics) to your **local Vajra Core** and delegates all
reasoning and execution to it.

## Develop

```powershell
cd vscode-extension
npm install
npm run build        # bundles to dist/extension.js
```

Then press <kbd>F5</kbd> in VS Code to launch an Extension Development Host.

## Configure

| Setting | Default | Notes |
|---------|---------|-------|
| `vajra.apiUrl` | `http://127.0.0.1:8760` | Vajra Local API base URL |
| `vajra.pairingToken` | — | must match `VAJRA_PAIRING_TOKEN` in the Core's `.env` |

## Commands

- **Vajra: Ask** — one-shot question with editor context
- **Vajra: Autonomous Task** — plan → build → test → review loop
- **Vajra: Run Tests**
- **Vajra: Review Workspace**
- **Vajra: Open Panel**

The side panel shows the live task plan, changed files, and any pending approvals.

## Package

```powershell
npm run package      # -> vajra-ai.vsix
```
