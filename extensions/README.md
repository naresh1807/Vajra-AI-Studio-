# Language & tool extensions

LSP servers, DAP adapters, formatters, linters, snippets, templates and project
scaffolds live here so the Core stays lean. Each pack is self-contained.

## Adding a language (no Core code changes)

The language engine is manifest-driven (manual v3.0 section 5). To teach the IDE
a new language you edit **`language-servers/servers.json`** and make its server
resolvable — nothing in `core/` changes.

Each entry in `packs`:

| field           | meaning |
|-----------------|---------|
| `id`            | unique label (shown in `/api/lsp/support` → `servers`) |
| `languages`     | editor language ids this pack answers for |
| `node`          | path segments under `language-servers/node_modules`, launched with the bundled `node` (works on Windows, unlike the `.bin/*.cmd` shims) |
| `command`       | *instead of* `node`: an executable resolved from `PATH` (you install the toolchain) |
| `args`          | appended to the launch argv |
| `pool`          | languages with the same `pool` share one server process |
| `lspLanguageId` | `{editorId: serverId}` overrides when they differ (e.g. `shell` → `shellscript`) |

### Bundled now

`npm install` in `language-servers/` pulls: **pyright** (python),
**typescript-language-server** (ts/js/tsx/jsx), **vscode-langservers-extracted**
(json, html, css/scss/less), **bash-language-server** (shell), plus **prettier**
for formatting.

### PATH-resolved (install the toolchain yourself)

Declared but inactive until the binary is on `PATH`:

- **rust** — `rustup component add rust-analyzer`
- **go** — `go install golang.org/x/tools/gopls@latest`
- **c / cpp** — install `clangd` (LLVM)

`GET /api/lsp/support` reports `declared` (all manifest languages) and
`languages` (which ones actually resolved on this machine).

## Formatters

`core/runtime/format.py`: ruff for python, bundled prettier for
ts/js/json/css/scss/less/html/markdown/yaml/vue/graphql. Add a language by
extending `_PRETTIER_LANGS` or adding a branch.
