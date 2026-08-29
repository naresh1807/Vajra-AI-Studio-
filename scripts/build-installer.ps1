# Build the Vajra AI Studio Windows installer.
# Usage:  pwsh -File scripts/build-installer.ps1

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot

# cargo may not be on PATH in a shell opened before rustup was installed
$cargo = "$env:USERPROFILE\.cargo\bin"
if (Test-Path $cargo) { $env:Path = "$cargo;$env:Path" }

if (-not (Get-Command cargo -ErrorAction SilentlyContinue)) {
    throw "cargo not found. Install Rust from https://rustup.rs and reopen the shell."
}

Push-Location "$root\studio-desktop"
try {
    if (-not (Test-Path "node_modules")) { npm install }
    npm run tauri build
    $exe = Get-ChildItem "src-tauri\target\release\bundle\nsis\*-setup.exe" | Select-Object -First 1
    if ($exe) {
        Copy-Item $exe.FullName "$root\VajraAI-Setup.exe" -Force
        Write-Host "`nInstaller: $($exe.FullName)" -ForegroundColor Green
        Write-Host "Copied to: $root\VajraAI-Setup.exe" -ForegroundColor Green
    }
} finally {
    Pop-Location
}
