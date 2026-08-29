import * as vscode from "vscode";
import { VajraClient } from "./client";
import { VajraChatView } from "./chatView";
import { registerAssist } from "./assist";
import { registerCompletions } from "./completions";
import { registerTests } from "./tests";
import { registerMisc } from "./misc";
import { registerMarketplace } from "./marketplace";

export function activate(ctx: vscode.ExtensionContext): void {
  const client = new VajraClient();
  const view = new VajraChatView(client);

  ctx.subscriptions.push(
    vscode.window.registerWebviewViewProvider(VajraChatView.viewId, view, {
      webviewOptions: { retainContextWhenHidden: true },
    }),
    vscode.commands.registerCommand("vajra.openPanel", () => view.reveal()),
    vscode.commands.registerCommand("vajra.ask", async () => {
      const q = await vscode.window.showInputBox({ prompt: "Ask Vajra" });
      if (q) void view.ask(q);
    }),
    vscode.commands.registerCommand("vajra.autonomousTask", async () => {
      const g = await vscode.window.showInputBox({ prompt: "Autonomous task (plan → build → test → review)" });
      if (g) void view.startAgent(g);
    }),
    vscode.commands.registerCommand("vajra.runTests", () =>
      view.startAgent("Run the test suite and report pass/fail with any failing output."),
    ),
    vscode.commands.registerCommand("vajra.reviewWorkspace", () =>
      view.startAgent("Review the current working-tree diff for correctness, maintainability and regression risk."),
    ),
  );

  registerAssist(ctx, client);
  registerCompletions(ctx, client);
  registerTests(ctx, client);
  registerMisc(ctx, client);
  registerMarketplace(ctx);
}

export function deactivate(): void {}
