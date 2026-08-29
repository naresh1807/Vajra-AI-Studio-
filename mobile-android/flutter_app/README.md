# Vajra Mobile

Secure remote control / monitoring / approval client for the desktop Vajra Core
(manual v3.0 section 11). It does **not** run the model or toolchain locally.

## Use it today — no build required

Vajra Mobile also ships as a page served by the Core:

1. On the PC, run the Core LAN-bound: set `VAJRA_BIND_LAN=true` in `.env`, then
   `vajra-api`. (Only do this on a trusted Wi-Fi.)
2. Find the PC's LAN IP (`ipconfig` → IPv4).
3. On your phone (same Wi-Fi) open **`http://<pc-ip>:8760/mobile`**.
4. Enter that URL + the pairing token → Connect.

You can submit a computer task or a project task, watch progress, approve gated
actions, and stop a run.

## Native Flutter app (this folder)

Same functionality as a proper APK. Needs the Flutter SDK + Android toolchain
(not installed on the dev machine yet).

```powershell
# once Flutter is installed:
cd mobile-android/flutter_app
flutter create --org ai.vajra --project-name vajra_companion --platforms android .
flutter pub get
flutter run            # on a connected device / emulator
flutter build apk --release   # -> build/app/outputs/flutter-apk/app-release.apk
```

`flutter create` scaffolds the missing `android/` gradle project around the
existing `lib/` + `pubspec.yaml`.

## Files

- `lib/api.dart` — `/api/*` client (health, ping, projects, computer/run,
  agent/run, agent/runs, agent/stop, approvals)
- `lib/main.dart` — pairing screen + New / Tasks / Approvals tabs, 2s polling
