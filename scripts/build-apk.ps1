<#
  Builds the Vajra Mobile release APK and copies it to ./VajraMobile.apk.
  Requires the toolchain from scripts/install-flutter.ps1 + install-toolchains.ps1
  (Flutter 3.47, JDK 17, Android SDK 36).
#>
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent

$env:JAVA_HOME    = 'C:\Users\DELL\dev\jdk\jdk-17.0.20.1+1'
$env:ANDROID_HOME = 'C:\Users\DELL\dev\android'
$flutter = 'C:\Users\DELL\dev\flutter\bin\flutter.bat'

Push-Location (Join-Path $repo 'mobile-android\flutter_app')
try {
  $apk = 'build\app\outputs\flutter-apk\app-release.apk'
  if (Test-Path $apk) { Remove-Item $apk -Force }   # never publish a stale artifact

  & $flutter pub get;            if ($LASTEXITCODE) { throw "flutter pub get failed ($LASTEXITCODE)" }
  & $flutter test;               if ($LASTEXITCODE) { throw "flutter test failed ($LASTEXITCODE)" }
  & $flutter build apk --release; if ($LASTEXITCODE) { throw "flutter build apk failed ($LASTEXITCODE) - check your internet connection (Gradle downloads plugins)" }
  if (-not (Test-Path $apk)) { throw "build reported success but $apk is missing" }

  Copy-Item $apk (Join-Path $repo 'VajraMobile.apk') -Force
  Write-Host "`n-> $(Join-Path $repo 'VajraMobile.apk')  ($([math]::Round((Get-Item $apk).Length/1MB,1)) MB)" -ForegroundColor Green
} finally {
  Pop-Location
}
