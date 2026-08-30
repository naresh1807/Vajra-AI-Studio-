# Getting started

## 1. Prerequisites

- Windows 10/11, Python 3.12+, Node.js LTS, Git
- Rust (`rustup`) + WebView2 — for the native desktop app / installer
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
VAJRA_NEMOTRON_MODEL=nvidia/nemotron-3-super-120b-a12b
VAJRA_PAIRING_TOKEN=<pick a long random string>
```

Run:

```powershell
pytest -q          # ~70 tests
vajra-api          # http://127.0.0.1:8760  (check /api/health)
```

The bundled language servers and formatters install with the frontend:

```powershell
cd extensions/language-servers && npm install && cd ../..
```

## 3. Vajra AI Studio (the IDE)

```powershell
cd legacy/studio-desktop
npm install
npm run dev        # browser UI on http://localhost:1420
# or:
npm run tauri dev  # native window
```

On the same machine no token is needed (the Core's device secret is read from
`data/device.json`). From a phone or another machine, set a password with
**Vajra: Set Password** and log in with it.

## 4. VS Code extension (optional)

```powershell
cd vscode-extension && npm install && npm run build
```

Open the folder in VS Code, press F5, set `vajra.pairingToken`, use the **Vajra** panel.

## 5. One-shot dev stack

```powershell
pwsh -File scripts/dev.ps1        # Core + Studio together
```

## 6. Build the installer

```powershell
cd legacy/studio-desktop
npm run tauri build              # -> src-tauri/target/release/bundle/nsis/*-setup.exe
```

## Smoke test the autonomous loop

With the Core running and a valid model key:

```powershell
$h = @{ "X-Vajra-Token" = "<token>"; "Content-Type" = "application/json" }
$body = @{ goal = "create hello.txt containing the word vajra, then run the tests"; workspace_root = "E:\some\project" } | ConvertTo-Json
$run = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8760/api/agent/run -Headers $h -Body $body
Invoke-RestMethod -Uri "http://127.0.0.1:8760/api/agent/runs/$($run.id)" -Headers $h   # poll
```
