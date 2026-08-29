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

## Status

🟢 verified end-to-end · 🟡 implemented, integration-testing · 🔵 in development · ⚪ planned

| Area | | |
|---|---|---|
| Core API + orchestrator + agents | 🟢 | 140 tests; autonomous loop verified greenfield + bug-fix against live Nemotron |
| Tool registry + policy + approvals | 🟢 | typed tools, risk levels, elevated calls park for approval, critical blocked |
| Git checkpoint / diff / rollback | 🟢 | `vajra/*` tags, per-write diff+rollback, restore touches only Vajra changes |
| Language engine (LSP/DAP/format) | 🟢 | 17 languages resolve (pyright, tsserver, clangd, gopls, rust-analyzer, …) |
| RAG semantic index | 🟢 | offline lexical vectors by default; OpenAI-compatible `/embeddings` opt-in |
| Computer agent | 🟢 | files/apps/PowerShell outside the workspace, approval-gated |
| OS-development agent | 🟢 | builds + boots a real multiboot kernel in QEMU, reads serial, iterates |
| Authorized-security agent | 🟢 | scope-gated defensive audits + connect-only checks, no offense |
| Device pairing + security hardening | 🟡 | random device secret, one-time PIN pairing, CORS lockdown, rate limit, `/api/v1` |
| **Vajra AI Studio** (Code-OSS fork) | 🟡 | builds + launches, Vajra extension loads as a built-in; full GUI QA pending |
| Vajra extension (chat/assist/tests/…) | 🟡 | `tsc` clean, every endpoint verified vs the Core; not click-tested in an Ext Host |
| Vajra Mobile (Android) | 🟡 | `GET /mobile` LAN page 🟢; native APK builds 🟡; secure QR pairing 🔵 |
| Windows installer | 🟢 | `studio\build.ps1 -Setup` → `VajraAIStudioSetup-x64.exe` (Inno) |
| CI (GitHub Actions) | 🟡 | `.github/workflows/ci.yml` — ruff/pytest, ext build, secret scan, Flutter |

See `docs/`, `studio/README.md`, and *Vajra AI Studio Complete Developer Manual v3.0*.
