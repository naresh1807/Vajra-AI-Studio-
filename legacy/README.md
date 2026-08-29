# legacy/

Superseded implementations, kept for reference. **Not part of the product.**

- `studio-desktop/` — the first Vajra AI Studio shell: Tauri 2 + React + Monaco,
  with a Rust sidecar that launched the Python Core. It worked (and its Windows
  installer built), but the v3.0 manual calls for a *VS Code-class* IDE, so the
  primary Studio is now the Code-OSS fork under [`../studio/`](../studio/) with
  everything Vajra-specific in the [`../vscode-extension/`](../vscode-extension/).
