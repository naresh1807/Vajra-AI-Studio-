/** Chat / Task webview. Supplies editor context to the local Vajra backend and
 *  streams task progress by polling the goal status endpoint. */
import * as vscode from "vscode";
import { VajraClient, RunStatus } from "./client";

export class VajraPanel implements vscode.WebviewViewProvider {
  public static readonly viewId = "vajra.chat";
  private view?: vscode.WebviewView;
  private pollTimer?: NodeJS.Timeout;

  constructor(private readonly client: VajraClient, private readonly ctx: vscode.ExtensionContext) {}

  resolveWebviewView(view: vscode.WebviewView): void {
    this.view = view;
    view.webview.options = { enableScripts: true };
    view.webview.html = this.html();
    view.webview.onDidReceiveMessage((msg) => this.onMessage(msg));
    void this.refreshHealth();
  }

  reveal(): void {
    void vscode.commands.executeCommand("vajra.chat.focus");
  }

  private post(msg: unknown): void {
    void this.view?.webview.postMessage(msg);
  }

  private workspaceRoot(): string | undefined {
    return vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
  }

  private editorContext(): string {
    const ed = vscode.window.activeTextEditor;
    if (!ed) return "";
    const sel = ed.selection && !ed.selection.isEmpty ? ed.document.getText(ed.selection) : "";
    const rel = vscode.workspace.asRelativePath(ed.document.uri);
    return sel
      ? `Active file: ${rel}\nSelected code:\n\`\`\`\n${sel}\n\`\`\``
      : `Active file: ${rel}`;
  }

  private async refreshHealth(): Promise<void> {
    try {
      const h = await this.client.health();
      this.post({ type: "health", ok: h.status === "ok", models: h.models });
    } catch (e) {
      this.post({ type: "health", ok: false, error: String(e) });
    }
  }

  private async onMessage(msg: any): Promise<void> {
    if (msg.type === "ask") {
      this.post({ type: "thinking" });
      try {
        const ctx = this.editorContext();
        const reply = await this.client.chat(ctx ? `${ctx}\n\n${msg.text}` : msg.text);
        this.post({ type: "reply", text: reply });
      } catch (e) {
        this.post({ type: "error", text: String(e) });
      }
    } else if (msg.type === "autonomous") {
      await this.startAutonomous(msg.text);
    } else if (msg.type === "cancel" && msg.goalId) {
      await this.client.stopRun(msg.goalId);
    } else if (msg.type === "approve") {
      await this.client.resolveApproval(msg.approvalId, msg.verdict);
    }
  }

  async startAutonomous(text: string): Promise<void> {
    const root = this.workspaceRoot();
    if (!root) {
      this.post({ type: "error", text: "Open a folder first." });
      return;
    }
    try {
      await this.client.openProject(root);
      const ctx = this.editorContext();
      const run = await this.client.startRun(ctx ? `${text}\n\nContext:\n${ctx}` : text, root);
      this.post({ type: "goalStarted", goal: run });
      this.startPolling(run.id);
    } catch (e) {
      this.post({ type: "error", text: String(e) });
    }
  }

  private startPolling(goalId: string): void {
    if (this.pollTimer) clearInterval(this.pollTimer);
    this.pollTimer = setInterval(async () => {
      try {
        const status: RunStatus = await this.client.runStatus(goalId);
        const approvals = await this.client.listApprovals();
        this.post({ type: "goalUpdate", status, approvals });
        if (["passed", "failed"].includes(status.status)) {
          clearInterval(this.pollTimer);
          this.pollTimer = undefined;
        }
      } catch {
        /* keep polling */
      }
    }, 1500);
  }

  private html(): string {
    return /* html */ `<!DOCTYPE html><html><head><meta charset="utf-8" />
<style>
  body { font: 13px var(--vscode-font-family); color: var(--vscode-foreground); padding: 8px; }
  #status { font-size: 11px; opacity: .8; margin-bottom: 8px; }
  .msg { padding: 6px 8px; margin: 4px 0; border-radius: 6px; white-space: pre-wrap; }
  .user { background: var(--vscode-editor-inactiveSelectionBackground); }
  .vajra { background: var(--vscode-editor-selectionHighlightBackground); }
  .err { color: var(--vscode-errorForeground); }
  .task { font-size: 12px; padding: 2px 0; }
  .task .state { opacity: .7; }
  textarea { width: 100%; box-sizing: border-box; background: var(--vscode-input-background);
    color: var(--vscode-input-foreground); border: 1px solid var(--vscode-input-border); border-radius: 4px; }
  button { margin-top: 4px; margin-right: 4px; background: var(--vscode-button-background);
    color: var(--vscode-button-foreground); border: none; padding: 4px 10px; border-radius: 4px; cursor: pointer; }
  .approval { border: 1px solid var(--vscode-inputValidation-warningBorder); padding: 6px; border-radius: 4px; margin: 4px 0; }
</style></head><body>
  <div id="status">connecting to Vajra Core…</div>
  <div id="log"></div>
  <div id="tasks"></div>
  <div id="approvals"></div>
  <textarea id="input" rows="3" placeholder="Ask Vajra, or describe an autonomous task…"></textarea>
  <div>
    <button id="ask">Ask</button>
    <button id="run">Autonomous Task</button>
    <button id="cancel" style="display:none">Stop</button>
  </div>
<script>
  const vscode = acquireVsCodeApi();
  const log = document.getElementById('log');
  const tasksEl = document.getElementById('tasks');
  const approvalsEl = document.getElementById('approvals');
  let currentGoal = null;
  function add(cls, text) {
    const d = document.createElement('div'); d.className = 'msg ' + cls; d.textContent = text;
    log.appendChild(d); d.scrollIntoView();
  }
  document.getElementById('ask').onclick = () => {
    const t = input.value.trim(); if (!t) return;
    add('user', t); input.value = '';
    vscode.postMessage({ type: 'ask', text: t });
  };
  document.getElementById('run').onclick = () => {
    const t = input.value.trim(); if (!t) return;
    add('user', '▶ ' + t); input.value = '';
    vscode.postMessage({ type: 'autonomous', text: t });
  };
  document.getElementById('cancel').onclick = () => {
    if (currentGoal) vscode.postMessage({ type: 'cancel', goalId: currentGoal });
  };
  const input = document.getElementById('input');
  window.addEventListener('message', (e) => {
    const m = e.data;
    if (m.type === 'health') {
      document.getElementById('status').textContent = m.ok
        ? 'Vajra Core ● ' + (m.models ? JSON.stringify(m.models) : '')
        : 'Vajra Core offline — ' + (m.error || '');
    } else if (m.type === 'thinking') add('vajra', '…');
    else if (m.type === 'reply') add('vajra', m.text);
    else if (m.type === 'error') add('err', m.text);
    else if (m.type === 'goalStarted') {
      currentGoal = m.goal.id;
      document.getElementById('cancel').style.display = 'inline-block';
      add('vajra', 'Task started: ' + m.goal.id);
    } else if (m.type === 'goalUpdate') {
      renderTasks(m.status); renderApprovals(m.approvals);
      if (['passed','failed'].includes(m.status.status)) {
        document.getElementById('cancel').style.display = 'none';
        add('vajra', 'Task ' + m.status.status + '. Files changed: ' + (m.status.changed_files.join(', ') || 'none'));
      }
    }
  });
  function renderTasks(status) {
    tasksEl.innerHTML = '<b>Plan</b>';
    (status.tasks || []).forEach(t => {
      const d = document.createElement('div'); d.className = 'task';
      d.innerHTML = '• ' + t.title + ' <span class="state">[' + t.agent + ' · ' + t.state + ']</span>';
      tasksEl.appendChild(d);
    });
  }
  function renderApprovals(list) {
    approvalsEl.innerHTML = '';
    (list || []).forEach(a => {
      const d = document.createElement('div'); d.className = 'approval';
      d.innerHTML = '<b>Approval needed:</b> ' + a.tool_name + '<br><small>' + a.reason + '</small><br>';
      const ok = document.createElement('button'); ok.textContent = 'Approve';
      ok.onclick = () => vscode.postMessage({ type: 'approve', approvalId: a.id, verdict: 'approved' });
      const no = document.createElement('button'); no.textContent = 'Reject';
      no.onclick = () => vscode.postMessage({ type: 'approve', approvalId: a.id, verdict: 'rejected' });
      d.appendChild(ok); d.appendChild(no); approvalsEl.appendChild(d);
    });
  }
</script></body></html>`;
  }
}
