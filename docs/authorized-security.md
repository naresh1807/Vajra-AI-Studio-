# Authorized security engineering (Phase 10)

Vajra's security mode is **defensive**. It helps you audit and harden your own
project, and run *connect-only* checks against systems you are explicitly
authorized to test. It has no exploitation, DoS, brute-force, persistence, or
detection-evasion capability, and the agent declines requests for them.

## Two tiers

### Defensive audits — no scope, no network

Run against the open project directly:

| Tool | What it does |
|---|---|
| `dependency_audit` | known-CVE check via `pip-audit` / `npm audit` if installed |
| `secret_scan` | committed API keys, tokens, private-key blocks (skips `.env.example`) |
| `config_audit` | sensitive files not git-ignored, permissive file modes, root Docker containers |

### Active checks — require an authorized scope + approval

`port_scan` (TCP connect, open/closed only) and `http_audit` (one GET: security
headers, version disclosure, TLS summary) only run against a target that a
**scope profile** lists, and every call pauses for your approval.

## Scope profiles

Stored per project at `.vajra/security/<name>.json`. Create one via
`POST /api/security/scopes` or the Studio Security panel:

```json
{
  "name": "acme-webapp-q3",
  "authorized_targets": ["10.0.5.0/24", "*.staging.acme.example"],
  "authorized_ports": [80, 443, 8080],
  "techniques": ["port-scan", "web-audit"],
  "authorization_ref": "PENTEST-2026-114 (signed SOW on file)",
  "expires_at": 1788200000,
  "notes": "staging only, business hours"
}
```

Rules enforced by `ScopeProfile.permits()`:

- Forbidden techniques (exploit, dos, bruteforce, exfil, persistence, evasion, …)
  are **never** permitted, regardless of the profile.
- The scope must not be expired.
- The technique must be listed.
- The target must match a listed host / IP / CIDR / domain glob.
- **Public** targets additionally require a non-empty `authorization_ref` and an
  explicit `expires_at`. Loopback / RFC-1918 targets must still be listed.
- If `authorized_ports` is set, the port must be in it.

## API

```
GET  /api/security/scopes?root=<project>
POST /api/security/scopes            {name, root, authorized_targets, techniques, ...}
POST /api/security/run               {instruction, root}
GET  /api/security/runs/{id}
```
