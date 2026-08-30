/** Status bar, semantic search, git checkpoint, project sync, run. */
import * as vscode from "vscode";
import { VajraClient } from "./client";
import { CoreManager } from "./core";

async function runProject(client: VajraClient, root: string | undefined, kind: string) {
  if (!root) {
    void vscode.window.showWarningMessage("Open a folder first.");
    return;
  }
  let plan;
  try {
    plan = await client.runPlan(root, kind);
  } catch (e) {
    void vscode.window.showErrorMessage(`Vajra: ${e}`);
    return;
  }
  let command = plan.command;
  if (!command) {
    command = (await vscode.window.showInputBox({ prompt: `No ${kind} command detected — enter one` })) ?? "";
    if (!command) return;
  } else {
    const alt = Object.entries(plan.alternatives).map(([k, v]) => ({ label: `${k}: ${v}`, cmd: v }));
    const pick = await vscode.window.showQuickPick(
      [{ label: `${kind}: ${command}${plan.framework ? `  (${plan.framework})` : ""}`, cmd: command }, ...alt],
      { placeHolder: `Vajra: ${kind}` },
    );
    if (!pick) return;
    command = pick.cmd;
  }
  await vscode.window.withProgress(
    { location: vscode.ProgressLocation.Notification, title: `Vajra: ${kind} — ${command}` },
    async () => {
      const r = await client.runStart(root, kind, command);
      if (r.url) {
        const open = await vscode.window.showInformationMessage(`Running at ${r.url}`, "Open");
        if (open === "Open") void vscode.env.openExternal(vscode.Uri.parse(r.url));
      } else if (r.exit_code !== undefined) {
        const ch = vscode.window.createOutputChannel("Vajra Run");
        ch.append(r.stdout ?? "");
        ch.show();
        void vscode.window.showInformationMessage(`${kind} exited ${r.exit_code}`);
      }
    },
  );
}

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
      let extra = h.models?.primary ?? "";
      const m = await client.models().catch(() => null);
      if (m?.primary) {
        const c = m.primary.circuit === "open" ? " ⚠ primary circuit open" : "";
        extra += `\n${m.primary.requests} req · ${m.primary.failures} fail · ${m.primary.avg_latency_ms}ms${c}`;
      }
      setState(h.status === "ok" ? "up" : "down", extra);
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
    vscode.commands.registerCommand("vajra.run", () => runProject(client, root(), "run")),
    vscode.commands.registerCommand("vajra.build", () => runProject(client, root(), "build")),
    vscode.commands.registerCommand("vajra.test", () => runProject(client, root(), "test")),
    vscode.commands.registerCommand("vajra.setPassword", async () => {
      try {
        const st = await client.authStatus();
        let current = "";
        if (st.configured) {
          const c = await vscode.window.showInputBox({
            password: true,
            prompt: "Current Vajra password (leave blank if VAJRA_PASSWORD is set in .env)",
          });
          if (c === undefined) return;
          current = c;
        }
        const next = await vscode.window.showInputBox({
          password: true,
          prompt: "New Vajra password (min 6 chars) — phones and other machines log in with this",
          validateInput: (v) => (v.trim().length >= 6 ? null : "at least 6 characters"),
        });
        if (!next) return;
        if (st.configured) await client.changePassword(current, next);
        else await client.authSetup(next);
        const pick = await vscode.window.showInformationMessage(
          "Vajra password set. On the phone, open the Vajra Mobile app (or a browser to the URL below) and log in.",
          "Copy phone URL",
        );
        if (pick === "Copy phone URL") {
          const base = vscode.workspace.getConfiguration("vajra").get<string>("apiUrl", "");
          await vscode.env.clipboard.writeText(base.replace("127.0.0.1", "<your-PC-Wi-Fi-IP>"));
        }
      } catch (e) {
        void vscode.window.showErrorMessage(`Vajra: ${e}`);
      }
    }),
  );
}
