# Vajra AI — Android companion app

**Phase 0 deliverable.** A secure remote command / monitoring / approval client for
the desktop Vajra Core. It does **not** run the model or toolchain locally.

## Scope for the MVP

- Pair with the desktop Core over the same private Wi-Fi / LAN (enter API URL + pairing token, or scan a QR shown by the Desktop App).
- Submit a goal, view task status / results.
- Approve or reject a gated action.
- Stop a running task.

## Screens

Home / PC Connection · Chat / Command · Projects · Active Tasks · Logs / Results · Approvals · Stop Task · Settings

## Stack

Flutter. Talks to the same `POST /api/v1/goals`, `GET /api/v1/goals/{id}`,
`POST /api/v1/tools/approve`, `POST /api/v1/tasks/{id}/cancel` endpoints as the other clients.

## Bootstrap (once Flutter SDK is installed)

```powershell
cd apps/android
flutter create --org ai.vajra --project-name vajra_companion .
# then add http/websocket client + the screens above
flutter run
```
