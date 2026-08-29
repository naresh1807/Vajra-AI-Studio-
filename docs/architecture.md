# Vajra AI — Architecture (Phase 1 state)

```
 Windows Desktop App      VS Code Extension        Android App (Phase 0 stub)
        |                        |                          |
        +------------------------+--------------------------+
                                 v
                    Vajra Local API  (api/, FastAPI + WS)
                    Authorization: Bearer <pairing token>
                                 |
                                 v
        +==================  VAJRA CORE  (core/)  ==================+
        |                                                          |
   Model Router (llm/)        Orchestrator (orchestrator/)     Policy Engine (policy/)
   primary: NIM/Nemotron      OBSERVE->PLAN->ACT->VERIFY        risk levels + approval
   fallback: local            bounded retries, task DAG          + critical blocklist
        |                          |                                 |
        +--------------------------+---------------------------------+
                                   v
                       Tool Registry (tools/)
        read/write/patch · search/tree · run_command · run_tests/lint/build
        git status/diff/checkpoint/restore
                                   |
                                   v
             Workspace  (host)  +  .vajra/ memory  +  SQLite (database/)
```

## Request lifecycle (`POST /api/v1/goals`)

1. `discover_workspace()` builds/loads `.vajra/project.json` (stack, commands, entrypoints).
2. `PlannerAgent.create_task_graph()` asks the model for a JSON task DAG; falls back to a
   deterministic `checkpoint → implement → test → review` plan.
3. Orchestrator loop, per ready task:
   - specialist agent proposes tool calls (one LLM turn with tool schemas),
   - `PolicyEngine.validate()` gates each call; elevated/high-risk calls park in the
     `ApprovalGate` until a client resolves them,
   - `ToolRegistry.execute()` runs the tool inside the workspace,
   - `_verify()` decides pass/fail from the tool results + agent's final message.
4. Failure → bounded retry; after the retry budget, a `debug + retest` pair is spliced in.
5. Every step emits a `VajraEvent` → `logs/task_events.jsonl`, `audit_events` table, and
   all subscribed WebSocket clients. Secrets are redacted before persistence.

## What is NOT here yet

- RAG / embeddings (Phase 5) — memory is deterministic JSONL for now.
- Computer agent, OS engineering, VM adapters, security scope profiles (Phases 4/6/7).
- Android app implementation (Phase 0 — placeholder only).
- Tauri packaging needs an icon set (`npx @tauri-apps/cli icon`).
