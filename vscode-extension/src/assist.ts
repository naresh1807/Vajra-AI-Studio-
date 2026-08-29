/** Assisted mode: right-click / Ctrl+K actions -> /api/assist, applied through
 *  VS Code's native diff editor so the user reviews before saving. */
import * as vscode from "vscode";
import { VajraClient } from "./client";

const PROSE = new Set(["explain", "security"]);

const ACTIONS: Array<{ id: string; label: string }> = [
  { id: "explain", label: "Explain" },
  { id: "fix", label: "Fix" },
  { id: "refactor", label: "Refactor" },
  { id: "optimize", label: "Optimize" },
  { id: "tests", label: "Write Tests" },
  { id: "document", label: "Document" },
  { id: "security", label: "Security Review" },
];

export function registerAssist(ctx: vscode.ExtensionContext, client: VajraClient) {
  const root = () => vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;

  async function run(action: string, instruction?: string) {
    const ed = vscode.window.activeTextEditor;
    const r = root();
    if (!ed || !r) {
      void vscode.window.showWarningMessage("Open a file in a folder first.");
      return;
    }
    const doc = ed.document;
    const sel = ed.selection.isEmpty ? "" : doc.getText(ed.selection);
    const rel = vscode.workspace.asRelativePath(doc.uri);

    await vscode.window.withProgress(
      { location: vscode.ProgressLocation.Notification, title: `Vajra: ${action}…` },
      async () => {
        try {
          const res = await client.assist(r, rel, doc.getText(), action, sel, instruction);
          if (PROSE.has(action) || (!res.new_content && res.text)) {
            const out = await vscode.workspace.openTextDocument({
              content: res.text,
              language: "markdown",
            });
            await vscode.window.showTextDocument(out, { viewColumn: vscode.ViewColumn.Beside, preview: true });
            return;
          }
          if (!res.new_content) {
            void vscode.window.showInformationMessage(res.text || "No change proposed.");
            return;
          }
          await showDiffAndApply(doc, res.new_content);
        } catch (e) {
          void vscode.window.showErrorMessage(`Vajra: ${e}`);
        }
      },
    );
  }

  for (const a of ACTIONS) {
    ctx.subscriptions.push(
      vscode.commands.registerCommand(`vajra.assist.${a.id}`, () => run(a.id)),
    );
  }
  ctx.subscriptions.push(
    vscode.commands.registerCommand("vajra.assist.edit", async () => {
      const instruction = await vscode.window.showInputBox({ prompt: "Tell Vajra what to change" });
      if (instruction) void run("edit", instruction);
    }),
  );
}

async function showDiffAndApply(doc: vscode.TextDocument, proposed: string) {
  const orig = doc.uri;
  const preview = orig.with({ scheme: "vajra-proposed" });
  const provider = new (class implements vscode.TextDocumentContentProvider {
    provideTextDocumentContent() {
      return proposed;
    }
  })();
  const reg = vscode.workspace.registerTextDocumentContentProvider("vajra-proposed", provider);
  await vscode.commands.executeCommand(
    "vscode.diff",
    orig,
    preview,
    `${doc.fileName.split(/[\\/]/).pop()} ↔ Vajra proposal`,
  );
  const pick = await vscode.window.showInformationMessage(
    "Apply Vajra's change?",
    { modal: false },
    "Apply & Save",
    "Discard",
  );
  reg.dispose();
  if (pick === "Apply & Save") {
    const edit = new vscode.WorkspaceEdit();
    edit.replace(orig, new vscode.Range(0, 0, doc.lineCount, 0), proposed);
    await vscode.workspace.applyEdit(edit);
    await doc.save();
  }
}
