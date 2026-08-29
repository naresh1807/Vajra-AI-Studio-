/** Status bar, semantic search, git checkpoint, project sync. */
import * as vscode from "vscode";
import { VajraClient } from "./client";
import { CoreManager } from "./core";

export function registerMisc(ctx: vscode.ExtensionContext, client: VajraClient, core: CoreManager) {
  const root = () => vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;

  const status = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
  status.command = "vajra.coreMenu";
  ctx.subscriptions.push(status);

  const setState = (s: "up" | "starting" | "down", model = "") => {
    status.text =
      s === "up" ? "$(sparkle) Vajra ●" : s === "starting" ? "$(sync~spin) Vajra…" : "$(sparkle) Vajra ○";
    status.tooltip =
      s === "up"
        ? `Vajra Core online${model ? ` — ${model}` : ""}`
        : s === "starting"
          ? "Starting Vajra Core…"
          : "Vajra Core offline — click to start";
    status.show();
  };
  setState("down");
  ctx.subscriptions.push(core.onState((s) => setState(s)));

  const refresh = async () => {
    try {
      const h = await client.health();
      setState(h.status === "ok" ? "up" : "down", h.models?.primary ?? "");
    } catch {
      setState("down");
    }
  };
  void refresh();
  const timer = setInterval(refresh, 15000);
  ctx.subscriptions.push({ dispose: () => clearInterval(timer) });

  ctx.subscriptions.push(
    vscode.commands.registerCommand("vajra.coreMenu", async () => {
      const up = await core.isUp();
      const pick = await vscode.window.showQuickPick(
        [
          { label: "$(comment-discussion) Open Vajra Panel", cmd: "vajra.openPanel" },
          up
            ? { label: "$(debug-restart) Restart Core", cmd: "vajra.restartCore" }
            : { label: "$(play) Start Core", cmd: "vajra.startCore" },
          { label: "$(stop) Stop Core", cmd: "vajra.stopCore" },
          { label: "$(output) Show Core Log", cmd: "vajra.showCoreLog" },
        ],
        { placeHolder: `Vajra Core is ${up ? "online" : "offline"}` },
      );
      if (pick) void vscode.commands.executeCommand(pick.cmd);
    }),
  );

  // open the workspace in the Core + build the semantic index
  if (root()) {
    client.openProject(root()!).then(() => client.ragReindex(root()!)).catch(() => {});
  }
  ctx.subscriptions.push(
    vscode.workspace.onDidChangeWorkspaceFolders(() => {
      const r = root();
      if (r) client.openProject(r).then(() => client.ragReindex(r)).catch(() => {});
    }),
  );

  ctx.subscriptions.push(
    vscode.commands.registerCommand("vajra.semanticSearch", async () => {
      const r = root();
      if (!r) return;
      const q = await vscode.window.showInputBox({ prompt: "Semantic search: describe what you're looking for" });
      if (!q) return;
      const { hits } = await client.ragSearch(r, q, 20);
      const pick = await vscode.window.showQuickPick(
        hits.map((h) => ({
          label: h.ref,
          description: `score ${h.score.toFixed(2)}`,
          detail: h.text.split("\n")[0].slice(0, 120),
          hit: h,
        })),
        { placeHolder: `${hits.length} results for "${q}"`, matchOnDetail: true },
      );
      if (!pick) return;
      const doc = await vscode.workspace.openTextDocument(vscode.Uri.joinPath(vscode.Uri.file(r), pick.hit.path));
      const ed = await vscode.window.showTextDocument(doc);
      const line = Math.max(0, pick.hit.start_line - 1);
      ed.revealRange(new vscode.Range(line, 0, line, 0), vscode.TextEditorRevealType.InCenter);
      ed.selection = new vscode.Selection(line, 0, line, 0);
    }),
    vscode.commands.registerCommand("vajra.checkpoint", async () => {
      const r = root();
      if (!r) return;
      const label = await vscode.window.showInputBox({ prompt: "Checkpoint label", value: "manual" });
      if (label === undefined) return;
      await client.gitCheckpoint(r, label || "manual");
      void vscode.window.showInformationMessage(`Vajra checkpoint created (vajra/${label || "manual"})`);
    }),
    vscode.commands.registerCommand("vajra.reindex", async () => {
      const r = root();
      if (!r) return;
      const s = await client.ragReindex(r);
      void vscode.window.showInformationMessage(
        `Vajra index: ${s.files} files, ${s.chunks} chunks (${s.embedder})`,
      );
    }),
  );
}
