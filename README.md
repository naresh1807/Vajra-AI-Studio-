# Vajra AI Studio

A private, local-first **AI-native IDE and computer agent**. A VS Code-class desktop
editor where you can write code manually, ask for inline assistance, or hand Vajra a
high-level goal and let it plan → edit → save → run → test → debug → review → report.

> Not a chatbot, not just a VS Code extension. The **desktop IDE (Vajra AI Studio)** is
> the product and the primary execution host. **Vajra Mobile** is a secure Android
> control client. An optional **VS Code extension** brings the same agent brain into VS
> Code. No public hosting required.

## Repository layout

| Path | What |
|------|------|
| `core/` | Vajra Core — `api/` (FastAPI + WS), `orchestrator/`, `agents/`, `llm/`, `rag/`, `tools/`, `policy/`, `memory/`, `workspace/`, `osdev/`, `security/`, `events/` |
| `database/` | SQLite store + repositories (Postgres-swappable) |
| `studio/` | **Vajra AI Studio** — the primary desktop IDE. A rebranded Code-OSS fork that bundles the Vajra extension. `scripts/bootstrap.ps1` + `scripts/build.ps1`. |
| `vscode-extension/` | The Vajra extension — panel, assisted edits, test explorer, semantic search, Core auto-start (built-in for `studio/`, also usable in stock VS Code) |
| `legacy/studio-desktop/` | **Legacy** — the earlier Tauri + React + Monaco prototype shell. Not the product; kept for reference only. |
| `mobile-android/flutter_app/` | Vajra Mobile — native Android companion (`scripts/build-apk.ps1`) |
| `extensions/` | Language/tool packs — LSP servers, DAP adapters, formatters, linters, templates |
| `config/models.yaml` | Model routing config (Nemotron/NIM primary, local fallback) |
| `tests/` | pytest suite |

## Quick start (Core + API)

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -e ".[dev]"
copy .env.example .env       # then set NVIDIA_API_KEY and VAJRA_PAIRING_TOKEN
pytest -q                    # run the test suite
vajra-api                    # start Vajra Core on http://127.0.0.1:8760
```

Check it is up: `curl http://127.0.0.1:8760/api/health`

Build the desktop IDE (**Vajra AI Studio**, the Code-OSS fork):

```powershell
cd studio
scripts\bootstrap.ps1        # clone + rebrand + bundle extension + npm ci  (~20 min)
scripts\build.ps1            # gulp compile  (~30 min)   -> VajraAIStudio-win32-x64\
scripts\build.ps1 -Setup     # ...also VajraAIStudioSetup-x64.exe
```

The extension starts the Python Core (`vajra-api`) automatically on launch.
The legacy Tauri shell (`legacy/studio-desktop/`) still runs via `npm run dev`
there, but it is not the product.

## Model layer

Agents only ever call the **model router** (`core/llm/router.py`). Provider and model
names are resolved from `config/models.yaml` + environment — never hard-coded. Primary is
NVIDIA NIM / Nemotron; fallback is any OpenAI-compatible local endpoint (Ollama, vLLM,
llama.cpp). Swapping providers needs no agent-code changes.

## Three modes

- **Manual** — write code directly: file tree, Monaco editor, tabs, save, terminal, Git.
- **Assisted** — inline completions, select-and-ask, right-click Explain / Fix / Refactor /
  Optimize / Write Tests / Document; every AI edit shown as a diff before applying.
- **Agent** — give a goal; Vajra scans, plans a task graph, edits, runs tests, debugs,
  reviews, commits, and shows the final diff.

## Safety model

- **Tool-mediated execution** — the LLM never gets a raw shell. Every action is a typed
  tool call validated by the policy engine (`core/policy/engine.py`).
- **Approval gates** — elevated/high-risk calls park until a client approves them.
  Critical patterns (disk format, disabling protections) are blocked outright.
- **Reversible** — Git checkpoints/tags before edit batches; every file write keeps
  diff + rollback data; rollback touches only Vajra-owned changes.
- **Observable** — every plan, tool call, patch, command and test emits a structured
  event (`logs/task_events.jsonl` + DB); secrets are redacted before persistence.
- **Bounded autonomy** — 2 same-strategy retries, then re-plan. No infinite loops.

## Status (manual v3.0 roadmap)

| Phase | | |
|---|---|---|
| 0 | Desktop + Android shells | ✅ desktop · Android stub |
| 1 | VS Code-like manual editor | ✅ Monaco, tree, tabs, save, terminal |
| 2 | Language support (LSP) | ✅ pyright + tsserver: diagnostics, completion, hover, definition, format |
| 3 | Nemotron assistant | ✅ right-click Fix/Refactor/… + Ctrl+K, diff-accept; inline completions (opt-in) |
| 4 | Autonomous coding loop | ✅ plan → edit → test → debug → review → commit; verified greenfield + bug-fix |
| 5 | Git + rollback | ✅ stage/commit/checkpoint/restore panel |
| 6 | Computer agent | ✅ files/apps/PowerShell outside the workspace, approval-gated |
| 7 | Android command/control | ✅ `GET /mobile` LAN page + native APK (`scripts/build-apk.ps1`) |
| 8 | Multi-language expansion | ✅ manifest-driven packs: +json/html/css/bash bundled, rust/go/clangd via PATH |
| 9 | OS development agent | ✅ build → boot kernel/ISO in QEMU, capture serial, iterate |
| 10 | Authorized security engineering | ✅ scope-gated: defensive audits + connect-only checks, no offense |

Plus: split editor (Ctrl+\), DAP debugging, dev-server management, command
palette / quick-open / project search, Problems panel, status bar,
project-memory learning loop.

See `docs/` and *Vajra AI Studio Complete Developer Manual v3.0*.
