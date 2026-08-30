/** First-run wizard + health check (master-prompt P35 / P36). */
import * as vscode from "vscode";
import { VajraClient } from "./client";

const ICON: Record<string, string> = { ok: "$(check)", missing: "$(circle-slash)", error: "$(error)" };

export function registerSetup(ctx: vscode.ExtensionContext, client: VajraClient) {
  ctx.subscriptions.push(
    vscode.commands.registerCommand("vajra.healthCheck", async () => {
      let d;
      try {
        d = await client.doctor();
      } catch (e) {
        void vscode.window.showErrorMessage(`Vajra Core not reachable: ${e}`);
        return;
      }
      const items = d.checks.map((c) => ({
        label: `${ICON[c.status] ?? "$(question)"} ${c.name}`,
        description: c.status + (c.required ? " · required" : ""),
        detail: c.detail,
      }));
      await vscode.window.showQuickPick(items, {
        placeHolder: d.ok ? "Environment OK — required tools present" : "Some required tools are missing",
        matchOnDetail: true,
      });
    }),

    vscode.commands.registerCommand("vajra.firstRun", async () => {
      const st = await client.setupState().catch(() => null);
      if (!st) {
        void vscode.window.showErrorMessage("Vajra Core not reachable.");
        return;
      }
      const d = await client.doctor();
      const missing = d.checks.filter((c) => c.required && c.status !== "ok").map((c) => c.name);
      if (missing.length) {
        void vscode.window.showWarningMessage(`Missing required: ${missing.join(", ")}. Run "Vajra: Health Check".`);
      }
      const folder = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
      if (folder) await client.setupComplete(folder);
      void vscode.window.showInformationMessage(
        `Vajra AI Studio is set up. Device ${st.device_id}. Open the Vajra panel to start.`,
      );
      void vscode.commands.executeCommand("vajra.openPanel");
    }),
  );

  // offer the wizard once, on first activation with a folder open
  client
    .setupState()
    .then((s) => {
      if (!s.completed && vscode.workspace.workspaceFolders?.length) {
        void vscode.window
          .showInformationMessage("Welcome to Vajra AI Studio — run first-time setup?", "Set up", "Later")
          .then((p) => p === "Set up" && vscode.commands.executeCommand("vajra.firstRun"));
      }
    })
    .catch(() => {});
}
