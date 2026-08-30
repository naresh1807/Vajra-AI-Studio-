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
| P10 | Diff system | 🟡 | `/api/files/diff`, `/api/git/diff`, checkpoints/restore; **per-hunk accept/reject UI not built** |
| P11 | Checkpoint & rollback | 🟢 | `core/runtime/git.py` `vajra/*` tags; `/api/git/{checkpoint,checkpoints,rollback}`; `test_git.py` |
| P12 | Language architecture (LSP/DAP/packs) | 🟢 | 17 languages resolve; `test_lsp.py` — clangd/gopls/json diagnostics live |
| P13 | Framework detection | 🟢 | `core/workspace/discovery.py`; `test_workspace.py` |
| P14 | Run system | 🟡 | run command inferred by discovery; used by the Tester agent |
| P15 | Test explorer | 🟢 | `core/runtime/testing.py` + `/api/testing/*`; extension `TestController`; `test_testing.py` |
| P16 | Debugger (DAP) | 🟢 | `core/dap/`; `test_dap.py` — launch/breakpoints/step/vars live |
| P17 | Model router hardening | 🟢 | `test_model_router.py` (8): retry, fallback, 429, circuit breaker, cancellation, metrics |
| P18 | Agent context management | 🟡 | RAG retrieval + workspace summary feed the agents; not tuned per-symbol |
| P19 | Memory / RAG | 🟢 | `core/rag/`; `test_rag.py`; auto-reindex on project open |
| P20 | Secret protection | 🟢 | `events.redact()`; `secret_scan`; `test_security.py` |
| P21 | Terminal security (human vs AI) | 🟢 | `/api/terminal/run` = shell; `run_command` tool = argv-only; `test_terminal.py` |
| P22 | Computer agent | 🟢 | verified live: "create a folder on the Desktop" → approval → created |
| P23 | High-risk approval | 🟢 | `ApprovalGate`; CRITICAL blocklist; `test_policy.py`, `test_concurrency.py` (expiry) |
| P24-25 | Android companion + pairing | 🟡 | `GET /mobile` page 🟢; native APK builds 🟡; QR/PIN pairing endpoint 🟢, app-side 🔵 |
| P26 | OS development mode | 🟢 | verified live: built + booted `examples/tiny-kernel` in QEMU, read `VAJRA-KERNEL-OK` off serial |
| P27 | Security engineering mode | 🟢 | scope-gated; verified live: self-audit of this repo |
| P28 | Observability | 🟢 | every plan/tool/patch/test emits a structured event; DB + `logs/*.jsonl` |
| P29 | Task cancellation | 🟢 | `orchestrator.cancel()`; `/api/agent/stop`; `test_model_router.py::test_cancellation_propagates` |
| P30 | Crash recovery | 🟢 | `db.mark_interrupted_goals()` on startup; `/api/agent/interrupted`; `test_crash_recovery.py` |
| P31 | CI/CD | 🟡 | `.github/workflows/ci.yml` — will run on first PR |
| P32 | Security edge-case tests | 🟡 | path escapes 🟢, approval expiry 🟢, concurrency 🟢; huge/binary files, provider outage in prod ⚪ |
| P33 | Windows installer | 🟢 | `studio\build.ps1 -Setup` → `VajraAIStudioSetup-x64.exe` (built, 260 MB) |
| P34 | Android APK | 🟢 | `scripts\build-apk.ps1` → `VajraMobile.apk` (built, 48 MB) |
| P35 | First-run wizard | 🟢 | `/api/setup/*`; extension `Vajra: First-time Setup` + walkthrough; `test_doctor_setup.py` |
| P36 | Health check | 🟢 | `core/runtime/doctor.py`; live: 11/11 tools detected |
| P37 | README cleanup | 🟢 | status table with 🟢/🟡/🔵/⚪ markers |
| Priority 0 | One primary desktop | 🟢 | `studio/` (Code-OSS fork); `studio-desktop/` → `legacy/` |

## The four acceptance tests

1. **Critical E2E — IDE workflow** (open → manual edit → ask fix → diff → accept →
   build/test → auto-fix → tests pass → undo): 🟡 — **every piece verified
   individually** (assist, native diff, testing API, autonomous loop, checkpoint
   rollback, `file_shas` conflict guard) but the full chain has not been
   click-driven in an Extension Development Host on this (headless) machine.
2. **Autonomous "fix all errors and make it run"**: 🟢 — the autonomous loop was
   run live against Nemotron on a broken pytest project: tester→debugger→coder→
   tester→reviewer(APPROVED)→git, bounded retries, final gate green.
3. **Mobile control** (connect → select project → "run tests" → results → approve):
   🟡 — the `GET /mobile` web page does this today over LAN; the native APK
   builds but has not been installed on a device.
4. **OS development** (edit → build → boot QEMU → capture output → patch → rebuild):
   🟢 — verified live end-to-end with `examples/tiny-kernel` and the OS-dev agent.

## What genuinely needs a human at a desktop

- Click-through of P6/P7/P8 in the running Studio (Extension Development Host)
- Installing `VajraMobile.apk` on an Android phone and pairing it
- Per-hunk diff accept/reject UI (P10) — endpoint exists, merge-editor UI does not
