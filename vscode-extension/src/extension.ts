import * as vscode from "vscode";
import { VajraClient } from "./client";
import { VajraPanel } from "./panel";

export function activate(context: vscode.ExtensionContext): void {
  const client = new VajraClient();
  const panel = new VajraPanel(client, context);

  context.subscriptions.push(
    vscode.window.registerWebviewViewProvider(VajraPanel.viewId, panel, {
      webviewOptions: { retainContextWhenHidden: true },
    }),
  );

  const reveal = () => vscode.commands.executeCommand("vajra.chat.focus");

  context.subscriptions.push(
    vscode.commands.registerCommand("vajra.openPanel", reveal),

    vscode.commands.registerCommand("vajra.ask", async () => {
      const q = await vscode.window.showInputBox({ prompt: "Ask Vajra" });
      if (!q) return;
      await reveal();
      try {
        const reply = await client.chat(q);
        void vscode.window.showInformationMessage(reply.slice(0, 300));
      } catch (e) {
        void vscode.window.showErrorMessage(String(e));
      }
    }),

    vscode.commands.registerCommand("vajra.autonomousTask", async () => {
      const goal = await vscode.window.showInputBox({
        prompt: "Describe the autonomous task (Vajra will plan → build → test → review)",
      });
      if (!goal) return;
      await reveal();
      await panel.startAutonomous(goal);
    }),

    vscode.commands.registerCommand("vajra.runTests", async () => {
      await reveal();
      await panel.startAutonomous("Run the test suite and report pass/fail with failing output.");
    }),

    vscode.commands.registerCommand("vajra.reviewWorkspace", async () => {
      await reveal();
      await panel.startAutonomous(
        "Review the current working-tree diff for correctness, maintainability and regression risk.",
      );
    }),
  );

  client
    .health()
    .then((h) => vscode.window.setStatusBarMessage(`Vajra Core ● ${h.status}`, 4000))
    .catch(() => vscode.window.setStatusBarMessage("Vajra Core offline", 4000));
}

export function deactivate(): void {}
