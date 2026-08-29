<#
  Installs the optional external toolchains Vajra's language engine and OS-dev
  agent can use. Run from an ELEVATED PowerShell (winget machine-scope installs
  need UAC):

      Start-Process powershell -Verb RunAs -ArgumentList '-File','scripts\install-toolchains.ps1'

  Already handled without admin (do not need this script):
    - pip-audit        -> pip install pip-audit   (in .venv)
    - rust-analyzer    -> rustup component add rust-analyzer
    - Flutter SDK      -> scripts/install-flutter.ps1
#>
$ErrorActionPreference = 'Continue'

function Winget($id, $label) {
  Write-Host "== $label ($id) ==" -ForegroundColor Cyan
  winget install --id $id --exact --silent --accept-package-agreements --accept-source-agreements
}

Winget 'GoLang.Go'                          'Go (for gopls)'
Winget 'SoftwareFreedomConservancy.QEMU'    'QEMU (OS-dev agent: boot kernels/ISOs)'
Winget 'LLVM.LLVM'                          'LLVM / clangd (C/C++ language server)'

Write-Host "`n== gopls ==" -ForegroundColor Cyan
$go = 'C:\Program Files\Go\bin\go.exe'
if (Test-Path $go) {
  & $go install golang.org/x/tools/gopls@latest
  Write-Host "gopls -> $env:USERPROFILE\go\bin\gopls.exe"
} else {
  Write-Host "Go not found on PATH yet - open a new shell and run: go install golang.org/x/tools/gopls@latest"
}

Write-Host "`nDone. Restart the Vajra Core so it re-scans PATH." -ForegroundColor Green
Write-Host "Verify:  curl -s localhost:8760/api/lsp/support | python -m json.tool"
Write-Host "         curl -s -H 'X-Vajra-Token: <token>' localhost:8760/api/osdev/providers"
