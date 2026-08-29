# Vajra AI

**Personal Autonomous Engineering Agent** — a private, local-first AI software engineer
and computer agent. You give a high-level goal; Vajra plans → builds → tests → debugs →
reviews → completes, coordinating VS Code, files, terminals, Git, Docker and VMs.

> Not a SaaS. The Windows **Desktop App** is the primary execution host; the **Android**
> app is a secure companion; the **VS Code extension** is the primary engineering surface.
> No public hosting is required.

## Repository layout

| Path | What |
|------|------|
| `core/` | Vajra Core — orchestrator, agents, tools, model router, policy, memory, workspace discovery |
| `api/` | Vajra Local API (FastAPI + WebSocket) — the secure localhost surface for all clients |
| `database/` | SQLite store + repositories (Postgres-swappable) |
| `vscode-extension/` | TypeScript VS Code coordinator extension |
| `apps/desktop/` | Windows desktop shell (React + Vite, Tauri wrapper) |
| `apps/android/` | Android companion app (placeholder — Phase 0) |
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

Check it is up:

```powershell
curl http://127.0.0.1:8760/health
```

## Model layer

Agents only ever call the **model router** (`core/llm/router.py`). Provider and model
names are resolved from `config/models.yaml` + environment — never hard-coded. Primary is
NVIDIA NIM / Nemotron; fallback is any OpenAI-compatible local endpoint (Ollama, vLLM,
llama.cpp). Swapping providers needs no agent-code changes.

## Safety model

- **Tool-mediated execution** — the LLM never gets a raw shell. Every action is a typed
  tool call validated by the policy engine (`core/policy/engine.py`).
- **Approval gates** — elevated/high-risk calls park in the approval gate until a client
  approves them. Critical patterns (disk format, disabling protections) are blocked.
- **Reversible** — Git checkpoints/tags before edit batches; rollback touches only
  Vajra-owned changes.
- **Observable** — every plan, tool call, patch and test emits a structured event
  (`logs/task_events.jsonl` + `audit_events` table); secrets are redacted before persistence.
- **Bounded autonomy** — 2 same-strategy retries, then force a re-plan. No infinite loops.

## Roadmap

Phase 0 product shells → Phase 1 core developer foundation (**here**) → Phase 2 VS Code
coordinator → Phase 3 autonomous loop → Phase 4 computer agent → Phase 5 memory/RAG →
Phase 6 OS engineering → Phase 7 authorized security → Phase 8 voice/multimodal.

See `docs/` and the *Complete Developer Manual*.
