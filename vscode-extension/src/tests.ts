/** Native Test Explorer backed by the Core's /api/testing. */
import * as vscode from "vscode";
import { VajraClient } from "./client";

export function registerTests(ctx: vscode.ExtensionContext, client: VajraClient) {
  const ctrl = vscode.tests.createTestController("vajra", "Vajra Tests");
  ctx.subscriptions.push(ctrl);

  const root = () => vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
  const items = new Map<string, vscode.TestItem>();

  ctrl.resolveHandler = async () => {
    const r = root();
    if (!r) return;
    let discovered: { framework: string; tests: string[] };
    try {
      discovered = await client.testDiscover(r);
    } catch {
      return;
    }
    ctrl.items.replace([]);
    items.clear();
    const files = new Map<string, vscode.TestItem>();
    for (const id of discovered.tests) {
      const [file, ...rest] = id.split("::");
      let fileItem = files.get(file);
      if (!fileItem) {
        fileItem = ctrl.createTestItem(file, file, vscode.Uri.joinPath(vscode.Uri.file(r), file));
        files.set(file, fileItem);
        ctrl.items.add(fileItem);
      }
      const t = ctrl.createTestItem(id, rest.join(" › ") || id, fileItem.uri);
      fileItem.children.add(t);
      items.set(id, t);
    }
  };

  const runProfile = ctrl.createRunProfile("Run", vscode.TestRunProfileKind.Run, async (request) => {
    const r = root();
    if (!r) return;
    const run = ctrl.createTestRun(request);
    const targets: string[] = [];
    const collect = (t: vscode.TestItem) => {
      if (t.children.size) t.children.forEach(collect);
      else {
        targets.push(t.id);
        run.enqueued(t);
      }
    };
    (request.include ?? gatherAll(ctrl)).forEach(collect);
    try {
      const res = await client.testRun(r, request.include ? targets : undefined);
      const byId = new Map(res.cases.map((c) => [c.id, c.outcome]));
      for (const id of targets) {
        const item = items.get(id);
        if (!item) continue;
        const oc = byId.get(id);
        if (oc === "passed") run.passed(item);
        else if (oc === "skipped") run.skipped(item);
        else run.failed(item, new vscode.TestMessage(res.output.slice(-4000)));
      }
      run.appendOutput(res.output.replace(/\n/g, "\r\n"));
    } catch (e) {
      run.appendOutput(String(e));
    } finally {
      run.end();
    }
  });
  ctx.subscriptions.push(runProfile);

  ctx.subscriptions.push(
    vscode.commands.registerCommand("vajra.discoverTests", () => ctrl.resolveHandler?.(undefined)),
  );
  void ctrl.resolveHandler(undefined);
}

function gatherAll(ctrl: vscode.TestController): vscode.TestItem[] {
  const out: vscode.TestItem[] = [];
  ctrl.items.forEach((t) => out.push(t));
  return out;
}
