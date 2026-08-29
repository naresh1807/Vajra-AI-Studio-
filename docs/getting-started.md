# Getting started

## 1. Prerequisites

- Windows 10/11, Python 3.12+, Node.js LTS, Git
- (optional) Rust + WebView2 for the Tauri desktop window
- (optional) NVIDIA API key for hosted NIM / Nemotron

## 2. Vajra Core + API

```powershell
python -m venv .venv
.\.venv\Scripts\activate
pip install -e ".[dev]"
copy .env.example .env
```

Edit `.env`:

```
NVIDIA_API_KEY=nvapi-...
VAJRA_NEMOTRON_MODEL=nvidia/llama-3.3-nemotron-super-49b-v1
VAJRA_PAIRING_TOKEN=<pick a long random string>
```

Run:

```powershell
pytest -q          # 23 tests
vajra-api          # http://127.0.0.1:8760
```

## 3. VS Code extension

```powershell
cd vscode-extension
npm install
npm run build
```

Open this folder in VS Code, press F5. In the Extension Dev Host, set
`vajra.pairingToken` to the same value as `.env`, then use the **Vajra** side panel
or the `Vajra: Autonomous Task` command.

## 4. Desktop UI

```powershell
cd apps/desktop
npm install
npm run dev        # http://localhost:1420
```

Set the pairing token in **Settings**, then drive goals from **Chat / Goal**.

## 5. One-shot dev stack

```powershell
pwsh -File scripts/dev.ps1
```

## Smoke test the autonomous loop

With the Core running and a valid model key:

```powershell
$h = @{ "X-Vajra-Token" = "<token>"; "Content-Type" = "application/json" }
$body = @{ text = "create hello.txt containing the word vajra, then run the tests"; workspace_root = "E:\some\project" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8760/api/v1/goals -Headers $h -Body $body
```

Poll `GET /api/v1/goals/{id}` for the task graph and `GET /api/v1/diff/{id}` for changed files.
