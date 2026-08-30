# Acceptance status

Honest mapping of the *Final Hardening* master prompt to what has actually been
**run**, per rule P38 ("do not claim a phase complete until … an end-to-end
scenario passes").

Legend: 🟢 verified end-to-end · 🟡 implemented + unit/integration tested ·
🔵 in development · ⚪ planned

## Priorities

| | Priority | State | Evidence |
|---|---|---|---|
| P0 | Secure pairing (random device secret, PIN, revocation) | 🟢 | `test_pairing.py` (10) + live: `change-me-local-only` rejected, PIN pair→token→revoke over HTTP |
| P1 | `/api/v1` stable alias | 🟢 | `test_pairing.py::test_api_v1_alias` |
| P2 | API split into `deps.py` + `routers/*` | 🟢 | `main.py` 1029→111 lines; 176 tests unchanged |
| P3 | Device credentials | 🟢 | `core/security/pairing.py` + tests |
| P4 | CORS lockdown, rate limit, WS auth | 🟢 | `test_pairing.py::test_cors_not_wildcard`; middleware in `main.py` |
| P5 | Workspace path escape protection | 🟢 | `test_safepath.py` (14): `../`, symlink, junction (realpath), UNC, ADS, NUL, absolute-outside |
| P6 | Manual coding mode (full IDE) | 🟡 | inherited from Code-OSS; fork builds + launches; **not click-tested** |
| P7 | Assisted coding (explain/fix/…/diff) | 🟡 | `/api/assist` + `test_assist_agent.py`; extension `assist.ts` uses native diff; **not click-tested** |
| P8 | Autonomous agent loop | 🟢 | earlier: verified live vs Nemotron — greenfield app + a real bug-fix, 6/6 tasks, commit+tag |
| P9 | Human+AI collab / no silent clobber | 🟢 | `/api/files/write` 409 (`test_api.py`); agent `ToolContext.file_shas` (`test_fs_conflict.py`) |
| P10 | Diff system | 🟢 | `/api/files/diff`, `/api/git/diff`, checkpoints/restore; per-hunk apply below |
| P11 | Checkpoint & rollback | 🟢 | `core/runtime/git.py` `vajra/*` tags; `/api/git/{checkpoint,checkpoints,rollback}`; `test_git.py` |
| P12 | Language architecture (LSP/DAP/packs) | 🟢 | 17 languages resolve; `test_lsp.py` — clangd/gopls/json diagnostics live |
| P13 | Framework detection | 🟢 | `core/workspace/discovery.py`; `test_workspace.py` |
| P14 | Run system | 🟢 | `core/runtime/runner.py` `plan(root,kind)` + `/api/run/{plan,start}`; `test_discovery_run.py`; extension `Vajra: Run/Build/Test Project` |
| P15 | Test explorer | 🟢 | `core/runtime/testing.py` + `/api/testing/*`; extension `TestController`; `test_testing.py` |
| P16 | Debugger (DAP) | 🟢 | `core/dap/`; `test_dap.py` — launch/breakpoints/step/vars live |
| P17 | Model router hardening | 🟢 | `test_model_router.py` (8): retry, fallback, 429, circuit breaker, cancellation, metrics |
| P10+ | Per-hunk diff review | 🟢 | `vscode-extension/src/hunks.ts` LCS line-diff → hunks + `applyHunks(subset)`; Assisted "Apply hunk-by-hunk…" QuickPick (canPickMany) builds a partial `WorkspaceEdit`. Full merge-editor UI still needs a GUI session. |
| P18 | Agent context management | 🟢 | `core/agents/context.py` `build_context()`: task→semantic-search→diff→editor-focus→memory→summary, each size-capped (retrieved 6k / diff 4k / focus 4k), best-effort. `AgentContext.prompt_context()` assembles it; orchestrator + planner + every specialist use it. `/api/agent/run` takes `focus`. `tests/test_agent_context.py` |
| P19 | Memory / RAG | 🟢 | `core/rag/`; `test_rag.py`; auto-reindex on project open |
| P20 | Secret protection | 🟢 | `events.redact()` (logs/DB) + `core/security/redaction.py` `redact_secrets()` masks .env / key files / inline creds / PEM blocks / vendor key shapes at every model-facing chokepoint: `read_file` & `search_text` & `semantic_search` tools, agent `build_context`, ChatAgent auto-retrieval, `/api/assist` (refuses edits on secret files). `test_redaction.py`; `secret_scan`; `test_security.py` |
| P21 | Terminal security (human vs AI) | 🟢 | `/api/terminal/run` = shell (human); `run_command` tool = argv-only (AI) + policy `_HIGH_RISK_MARKERS` (pipe-to-shell, sudo, `rm -rf`, `git clean -fdx`, `dd`, `-g` installs) → approval; routine `pip install`/`npm ci`/`pytest` run free. `test_terminal.py`, `test_policy.py` |
| P22 | Computer agent | 🟢 | verified live: "create a folder on the Desktop" → approval → created |
| P23 | High-risk approval | 🟢 | `ApprovalGate` + CRITICAL blocklist now covers the full P23 list: format/wipe, boot config, shutdown/reboot, firewall + AV disable, git force-push / `reset --hard origin`, drop-database, credential + privilege changes. `test_policy.py` (16, incl. a param sweep); `test_concurrency.py` (expiry) |
| P24-25 | Android companion + pairing | 🟡 | `GET /mobile` page + native APK both do PIN pairing (`/api/pairing/redeem`) or raw token; desktop `Vajra: Pair a Phone` shows the PIN + LAN URL. `test_pairing.py::test_pairing_pin_flow_over_http` + Flutter widget tests. **Not run on a physical device** |
| P26 | OS development mode | 🟢 | verified live: built + booted `examples/tiny-kernel` in QEMU, read `VAJRA-KERNEL-OK` off serial |
| P27 | Security engineering mode | 🟢 | scope-gated; verified live: self-audit of this repo |
| P28 | Observability | 🟢 | every plan/tool/patch/test emits a structured event; DB + `logs/*.jsonl` |
| P29 | Task cancellation | 🟢 | `orchestrator.cancel()`; `/api/agent/stop`; `test_model_router.py::test_cancellation_propagates` |
| P30 | Crash recovery | 🟢 | `db.mark_interrupted_goals()` on startup; `/api/agent/interrupted`; `test_crash_recovery.py` |
| P31 | CI/CD | 🟢 | `.github/workflows/ci.yml` on push to `main` + PRs. core (ruff + pytest, Win/py3.12): 193 pass. extension (tsc/build/vsce), security (secret-scan + pip-audit): green. language-servers + Flutter are `continue-on-error` (live LSP / SDK timing). First real runs found + fixed: token-env mismatch, missing setup-python, an un-guarded QEMU test, LSP cold-start timeouts |
| P32 | Security edge-case tests | 🟢 | path escapes, approval expiry, concurrency, circuit breaker; huge-file truncation + binary-file flag (`test_files_edge.py`); provider-outage fallback (`test_model_router.py`) |
| P33 | Windows installer | 🟢 | `studio\build.ps1 -Setup` → `VajraAIStudioSetup-x64.exe` (built, 260 MB) |
| P34 | Android APK | 🟢 | `scripts\build-apk.ps1` → `VajraMobile.apk` (built, 48 MB) |
| P35 | First-run wizard | 🟢 | `/api/setup/*`; extension `Vajra: First-time Setup` + walkthrough; `test_doctor_setup.py` |
| P36 | Health check | 🟢 | `core/runtime/doctor.py`; live: 11/11 tools detected |
| P37 | README cleanup | 🟢 | status table with 🟢/🟡/🔵/⚪ markers |
| Priority 0 | One primary desktop | 🟢 | `studio/` (Code-OSS fork); `studio-desktop/` → `legacy/` |

## The four acceptance tests

1. **Critical E2E — IDE workflow** (open → manual edit → ask fix → diff → accept →
   build/test → auto-fix → tests pass → undo): 🟢 (headless) — `tests/test_acceptance_e2e.py`
   drives the whole chain through the HTTP API: open project → read (sha) → `/api/assist`
   fix → conflict-checked `/api/files/write` → `/api/git/checkpoint` → regression →
   `/api/git/rollback` restores the file. The GUI click-path of the same chain still
   needs an Extension Development Host session. (This test also caught a CRLF-file
   409 bug in `write_file`'s conflict check.)
2. **Autonomous "fix all errors and make it run"**: 🟢 — the autonomous loop was
   run live against Nemotron on a broken pytest project: tester→debugger→coder→
   tester→reviewer(APPROVED)→git, bounded retries, final gate green.
3. **Mobile control** (connect → select project → "run tests" → results → approve):
   🟡 — the `GET /mobile` web page does the whole flow today over LAN (PIN or
   token pairing); the native APK builds and its pairing + task/approval code is
   unit-tested, but it has not been installed on a physical device.
4. **OS development** (edit → build → boot QEMU → capture output → patch → rebuild):
   🟢 — verified live end-to-end with `examples/tiny-kernel` and the OS-dev agent.

## What genuinely needs a human at a desktop

- Click-through of P6/P7/P8 in the running Studio (Extension Development Host)
- Installing `VajraMobile.apk` on an Android phone and pairing it
- Full 3-way merge-editor UI (P10) — per-hunk QuickPick apply ships in the
  extension; the inline merge-editor view still needs a GUI session
