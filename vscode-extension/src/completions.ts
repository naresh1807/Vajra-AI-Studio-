/** Inline completions from the Core. Off unless `vajra.inlineCompletions` is on
 *  (hosted Nemotron is a reasoning model - only useful with a fast local model). */
import * as vscode from "vscode";
import { VajraClient } from "./client";

export function registerCompletions(ctx: vscode.ExtensionContext, client: VajraClient) {
  let lastAt = 0;
  const provider: vscode.InlineCompletionItemProvider = {
    async provideInlineCompletionItems(doc, pos) {
      if (!vscode.workspace.getConfiguration("vajra").get<boolean>("inlineCompletions", false)) {
        return { items: [] };
      }
      const root = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
      if (!root) return { items: [] };
      const offset = doc.offsetAt(pos);
      const full = doc.getText();
      const now = Date.now();
      lastAt = now;
      await new Promise((r) => setTimeout(r, 350));
      if (lastAt !== now) return { items: [] };
      try {
        const r = await client.complete(
          root,
          vscode.workspace.asRelativePath(doc.uri),
          full.slice(0, offset),
          full.slice(offset),
          doc.languageId,
        );
        if (!r.text || !r.text.trim()) return { items: [] };
        return { items: [{ insertText: r.text, range: new vscode.Range(pos, pos) }] };
      } catch {
        return { items: [] };
      }
    },
  };
  ctx.subscriptions.push(
    vscode.languages.registerInlineCompletionItemProvider({ pattern: "**" }, provider),
  );
}
