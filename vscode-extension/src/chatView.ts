/** The Vajra side panel: Assisted (chat) / Agent (autonomous) / Computer /
 *  OS Dev / Security. Talks to the local Core; renders the live plan +
 *  approval prompts. */
import * as vscode from "vscode";
import { Approval, RunRef, RunStatus, VajraClient } from "./client";

type Mode = "chat" | "agent" | "computer" | "osdev" | "security";
type Bubble = { role: "user" | "vajra" | "system" | "tool"; text: string; ok?: boolean };

export class VajraChatView implements vscode.WebviewViewProvider {
  static readonly viewId = "vajra.chat";
  private view?: vscode.WebviewView;
  private history: Array<{ role: string; content: string }> = [];
  private poll?: NodeJS.Timeout;

  constructor(private readonly client: VajraClient) {}

  resolveWebviewView(view: vscode.WebviewView) {
    this.view = view;
    view.webview.options = { enableScripts: true };
    view.webview.html = HTML;
    view.webview.onDidReceiveMessage((m) => this.onMessage(m));
    void this.refreshHealth();
  }

  reveal() {
    void vscode.commands.executeCommand("vajra.chat.focus");
  }

  private post(m: unknown) {
    void this.view?.webview.postMessage(m);
  }
  private root() {
    return vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
  }
  private ctxLine(): string {
    const ed = vscode.window.activeTextEditor;
    if (!ed) return "";
    const rel = vscode.workspace.asRelativePath(ed.document.uri);
    const sel = ed.selection.isEmpty ? "" : ed.document.getText(ed.selection);
    return sel ? `Active file ${rel}\nSelection:\n\`\`\`\n${sel}\n\`\`\`` : `Active file ${rel}`;
  }

  private async refreshHealth() {
    try {
      const h = await this.client.health();
      this.post({ type: "health", ok: h.status === "ok", models: h.models });
    } catch (e) {
      this.post({ type: "health", ok: false, error: String(e) });
    }
  }

  async startAgent(goal: string) {
    this.reveal();
    await this.onMessage({ type: "send", mode: "agent", text: goal });
  }

  async ask(text: string) {
    this.reveal();
    await this.onMessage({ type: "send", mode: "chat", text });
  }

  private async onMessage(m: any) {
    if (m.type === "ready") return this.refreshHealth();
    if (m.type === "resolveApproval") {
      await this.client.resolveApproval(m.id, m.verdict);
      return;
    }
    if (m.type === "stop" && m.id) {
      await this.client.stopRun(m.id).catch(() => {});
      return;
    }
    if (m.type !== "send") return;

    const mode: Mode = m.mode;
    const text: string = (m.text || "").trim();
    if (!text) return;
    const root = this.root();
    this.post({ type: "bubble", bubble: { role: "user", text } });

    try {
      if (mode === "chat") {
        this.history.push({ role: "user", content: text });
        const ctx = this.ctxLine();
        const r = await this.client.chat(ctx ? `${ctx}\n\n${text}` : text, this.history, root);
        for (const tc of r.tool_calls ?? [])
          this.post({ type: "bubble", bubble: { role: "tool", text: tc.tool, ok: tc.success } });
        this.history.push({ role: "assistant", content: r.reply });
        this.post({ type: "bubble", bubble: { role: "vajra", text: r.reply || "(no reply)" } });
        return;
      }
      if (mode === "agent") {
        if (!root) return this.post({ type: "bubble", bubble: { role: "system", text: "Open a folder first." } });
        await this.client.openProject(root);
        const run = await this.client.startRun(text, root, this.ctxLine());
        this.post({ type: "bubble", bubble: { role: "system", text: `Run ${run.id} started` } });
        this.startPoll(() => this.client.runStatus(run.id), run.id, true);
        return;
      }
      // computer / osdev / security -> RunRef pollers
      let started: { id: string };
      if (mode === "computer") started = await this.client.computerRun(text);
      else if (mode === "osdev") started = await this.client.osdevRun(text);
      else {
        if (!root) return this.post({ type: "bubble", bubble: { role: "system", text: "Open a folder first." } });
        started = await this.client.securityRun(text, root);
      }
      this.post({ type: "bubble", bubble: { role: "system", text: `${mode} run started` } });
      const getter =
        mode === "computer"
          ? () => this.client.computerRunStatus(started.id)
          : mode === "osdev"
            ? () => this.client.osdevRunStatus(started.id)
            : () => this.client.securityRunStatus(started.id);
      this.startPoll(getter, started.id, false);
    } catch (e) {
      this.post({ type: "bubble", bubble: { role: "system", text: `Error: ${e}` } });
    }
  }

  private startPoll(getter: () => Promise<RunStatus | RunRef>, id: string, isGraph: boolean) {
    if (this.poll) clearInterval(this.poll);
    this.poll = setInterval(async () => {
      try {
        const s: any = await getter();
        const approvals: Approval[] = await this.client.approvals();
        this.post({ type: "run", id, isGraph, status: s, approvals });
        if (["passed", "failed"].includes(s.status)) {
          clearInterval(this.poll);
          this.poll = undefined;
          if (s.reply) this.post({ type: "bubble", bubble: { role: "vajra", text: s.reply } });
          if (isGraph)
            this.post({
              type: "bubble",
              bubble: { role: "system", text: `Run ${s.status}. Changed: ${(s.changed_files ?? []).join(", ") || "none"}` },
            });
        }
      } catch {
        /* keep polling */
      }
    }, 1500);
  }
}

const HTML = /* html */ `<!DOCTYPE html><html><head><meta charset="utf-8"/><style>
 :root { color-scheme: dark light; }
 body { font: 13px var(--vscode-font-family); color: var(--vscode-foreground); margin: 0; padding: 8px; }
 #status { font-size: 11px; opacity: .75; margin-bottom: 6px; }
 .seg { display: flex; gap: 2px; margin-bottom: 8px; flex-wrap: wrap; }
 .seg button { flex: 1; background: var(--vscode-button-secondaryBackground); color: var(--vscode-button-secondaryForeground);
   border: none; padding: 3px 6px; font-size: 11px; border-radius: 3px; cursor: pointer; }
 .seg button.on { background: var(--vscode-button-background); color: var(--vscode-button-foreground); }
 .b { padding: 6px 8px; margin: 4px 0; border-radius: 6px; white-space: pre-wrap; }
 .b.user { background: var(--vscode-editor-inactiveSelectionBackground); }
 .b.vajra { background: var(--vscode-editor-selectionHighlightBackground); }
 .b.system { font-size: 11px; opacity: .7; }
 .b.tool { font-size: 11px; opacity: .8; font-family: var(--vscode-editor-font-family); }
 .plan { border: 1px solid var(--vscode-panel-border); border-radius: 6px; padding: 6px; margin: 6px 0; font-size: 12px; }
 .ptask { display: flex; justify-content: space-between; padding: 2px 0; }
 .badge { font-size: 10px; opacity: .8; }
 .approval { border: 1px solid var(--vscode-inputValidation-warningBorder); border-radius: 6px; padding: 6px; margin: 6px 0; }
 .approval button { margin-right: 6px; }
 textarea { width: 100%; box-sizing: border-box; background: var(--vscode-input-background); color: var(--vscode-input-foreground);
   border: 1px solid var(--vscode-input-border); border-radius: 4px; padding: 6px; }
 .go { margin-top: 4px; background: var(--vscode-button-background); color: var(--vscode-button-foreground);
   border: none; padding: 5px 14px; border-radius: 4px; cursor: pointer; }
</style></head><body>
 <div id="status">connecting…</div>
 <div class="seg" id="seg">
   <button data-m="chat" class="on">Assisted</button>
   <button data-m="agent">Agent</button>
   <button data-m="computer">Computer</button>
   <button data-m="osdev">OS Dev</button>
   <button data-m="security">Security</button>
 </div>
 <div id="log"></div>
 <div id="plan"></div>
 <div id="approvals"></div>
 <textarea id="in" rows="3" placeholder="Ask Vajra…"></textarea>
 <div><button class="go" id="go">Send</button><button class="go" id="stop" style="display:none">Stop</button></div>
<script>
 const vscode = acquireVsCodeApi();
 let mode = "chat", runId = null;
 const log = document.getElementById('log'), plan = document.getElementById('plan'),
   appr = document.getElementById('approvals'), input = document.getElementById('in');
 document.querySelectorAll('#seg button').forEach(b => b.onclick = () => {
   mode = b.dataset.m;
   document.querySelectorAll('#seg button').forEach(x => x.classList.toggle('on', x === b));
   input.placeholder = mode === 'chat' ? 'Ask Vajra…' : 'Describe the task…';
 });
 function bubble(x) {
   const d = document.createElement('div');
   d.className = 'b ' + x.role;
   d.textContent = (x.role === 'tool' ? (x.ok ? '✓ ' : '✗ ') + 'inspected · ' : '') + x.text;
   log.appendChild(d); d.scrollIntoView();
 }
 document.getElementById('go').onclick = () => {
   const t = input.value.trim(); if (!t) return;
   input.value = '';
   vscode.postMessage({ type: 'send', mode, text: t });
 };
 document.getElementById('stop').onclick = () => runId && vscode.postMessage({ type: 'stop', id: runId });
 input.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); document.getElementById('go').click(); } });
 window.addEventListener('message', e => {
   const m = e.data;
   if (m.type === 'health') {
     document.getElementById('status').textContent = m.ok
       ? 'Vajra Core ● ' + (m.models && m.models.primary ? m.models.primary : '')
       : 'Vajra Core offline — ' + (m.error || '');
   } else if (m.type === 'bubble') bubble(m.bubble);
   else if (m.type === 'run') {
     runId = ['passed','failed'].includes(m.status.status) ? null : m.id;
     document.getElementById('stop').style.display = runId ? 'inline-block' : 'none';
     const tasks = m.status.tasks || [];
     plan.innerHTML = tasks.length ? '<div class="plan"><b>Plan — ' + m.status.status + '</b>' +
       tasks.map(t => '<div class="ptask"><span>' + t.title + '</span><span class="badge">' + t.agent + ' · ' + t.state + '</span></div>').join('') + '</div>' : '';
     appr.innerHTML = '';
     (m.approvals || []).forEach(a => {
       const d = document.createElement('div'); d.className = 'approval';
       d.innerHTML = '<b>Approve ' + a.tool_name + '?</b><br><small>' + (a.reason || '') + '</small><br>';
       const y = document.createElement('button'); y.className = 'go'; y.textContent = 'Approve';
       y.onclick = () => vscode.postMessage({ type: 'resolveApproval', id: a.id, verdict: 'approved' });
       const n = document.createElement('button'); n.className = 'go'; n.textContent = 'Reject';
       n.onclick = () => vscode.postMessage({ type: 'resolveApproval', id: a.id, verdict: 'rejected' });
       d.appendChild(y); d.appendChild(n); appr.appendChild(d);
     });
   }
 });
 vscode.postMessage({ type: 'ready' });
</script></body></html>`;
