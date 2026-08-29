# Start the Vajra dev stack: Core API + Desktop UI.
# Usage:  pwsh -File scripts/dev.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

if (-not (Test-Path "$root\.venv")) {
    Write-Host "Creating venv..." -ForegroundColor Cyan
    python -m venv "$root\.venv"
    & "$root\.venv\Scripts\python.exe" -m pip install -e "$root[dev]"
}
if (-not (Test-Path "$root\.env")) {
    Copy-Item "$root\.env.example" "$root\.env"
    Write-Host "Created .env - set NVIDIA_API_KEY and VAJRA_PAIRING_TOKEN" -ForegroundColor Yellow
}

Write-Host "Starting Vajra Core on http://127.0.0.1:8760 ..." -ForegroundColor Green
$core = Start-Process "$root\.venv\Scripts\python.exe" -ArgumentList "-m","uvicorn","api.main:app","--host","127.0.0.1","--port","8760" -WorkingDirectory $root -PassThru

Start-Sleep -Seconds 3
Write-Host "Starting Desktop UI on http://localhost:1420 ..." -ForegroundColor Green
try {
    Push-Location "$root\apps\desktop"
    if (-not (Test-Path "node_modules")) { npm install }
    npm run dev
} finally {
    Pop-Location
    if ($core -and -not $core.HasExited) { Stop-Process -Id $core.Id -Force }
}
