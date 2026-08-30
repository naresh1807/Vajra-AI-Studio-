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
  private panel?: vscode.WebviewPanel;
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

  /** Open (or focus) the same chat as a roomy editor-area tab. */
  openTab() {
    if (this.panel) {
      this.panel.reveal(vscode.ViewColumn.Beside);
      return;
    }
    this.panel = vscode.window.createWebviewPanel(
      "vajra.chatTab",
      "Vajra",
      vscode.ViewColumn.Beside,
      { enableScripts: true, retainContextWhenHidden: true },
    );
    this.panel.webview.html = HTML;
    this.panel.webview.onDidReceiveMessage((m) => this.onMessage(m));
    this.panel.onDidDispose(() => (this.panel = undefined));
    void this.refreshHealth();
  }

  reveal() {
    void vscode.commands.executeCommand("vajra.chat.focus");
  }

  private post(m: unknown) {
    void this.view?.webview.postMessage(m);
    void this.panel?.webview.postMessage(m);
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
    if (m.type === "openTab") return this.openTab();
    if (m.type === "clear") {
      this.history = [];
      return;
    }
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
        this.post({ type: "bubble", bubble: { role: "system", text: "Working on it…" } });
        this.startAgentPoll(run.id);
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

  /** Agent runs: stream the human-readable activity feed as it happens. */
  private startAgentPoll(id: string) {
    if (this.poll) clearInterval(this.poll);
    let since = 0;
    this.poll = setInterval(async () => {
      try {
        const s = await this.client.runStatus(id, since);
        const approvals: Approval[] = await this.client.approvals();
        for (const a of s.activity ?? []) {
          this.post({ type: "activity", item: a });
          since = Math.max(since, a.i + 1);
        }
        this.post({ type: "run", id, isGraph: true, status: s, approvals });
        if (["passed", "failed"].includes(s.status)) {
          clearInterval(this.poll);
          this.poll = undefined;
        }
      } catch {
        /* keep polling */
      }
    }, 1200);
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
 :root { color-scheme: dark light; --gap: 10px; }
 * { box-sizing: border-box; }
 html, body { height: 100%; }
 body { font: 13.5px/1.55 var(--vscode-font-family); color: var(--vscode-foreground);
   margin: 0; display: flex; flex-direction: column; }
 header { display: flex; align-items: center; gap: 8px; padding: 8px 10px;
   border-bottom: 1px solid var(--vscode-panel-border); flex-shrink: 0; }
 #status { font-size: 11.5px; opacity: .8; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
 #status .dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%;
   background: var(--vscode-testing-iconFailed, #e55); margin-right: 6px; vertical-align: middle; }
 #status.ok .dot { background: var(--vscode-testing-iconPassed, #4c4); }
 .iconbtn { background: none; border: none; color: var(--vscode-foreground); opacity: .7;
   cursor: pointer; font-size: 14px; padding: 2px 4px; border-radius: 4px; }
 .iconbtn:hover { opacity: 1; background: var(--vscode-toolbar-hoverBackground); }
 .seg { display: flex; gap: 3px; padding: 8px 10px 0; flex-wrap: wrap; flex-shrink: 0; }
 .seg button { flex: 1 1 auto; background: var(--vscode-button-secondaryBackground);
   color: var(--vscode-button-secondaryForeground); border: none; padding: 4px 8px;
   font-size: 11.5px; border-radius: 4px; cursor: pointer; }
 .seg button.on { background: var(--vscode-button-background); color: var(--vscode-button-foreground); }
 #log { flex: 1; overflow-y: auto; padding: 10px; display: flex; flex-direction: column; gap: 7px; }
 #log:empty::after { content: "Ask a question, or describe a task for the agent."; opacity: .45; font-size: 12px; }
 .b { padding: 8px 11px; border-radius: 10px; white-space: pre-wrap; word-break: break-word; max-width: 92%; }
 .b.user { background: var(--vscode-editor-inactiveSelectionBackground); align-self: flex-end; }
 .b.vajra { background: var(--vscode-editor-selectionHighlightBackground); align-self: flex-start; }
 .b.system { font-size: 11.5px; opacity: .7; align-self: center; background: none; padding: 2px; }
 .b.tool { font-size: 11.5px; opacity: .85; font-family: var(--vscode-editor-font-family);
   align-self: flex-start; background: var(--vscode-textCodeBlock-background); }
 .b pre, .b code { font-family: var(--vscode-editor-font-family); font-size: 12.5px; }
 .b pre { background: var(--vscode-textCodeBlock-background); padding: 8px; border-radius: 6px; overflow-x: auto; }
 .act { align-self: stretch; font-size: 12px; line-height: 1.5; padding: 1px 2px; white-space: pre-wrap; word-break: break-word; }
 .act.goal { font-weight: 600; font-size: 13px; margin-top: 2px; }
 .act.plan { opacity: .95; padding: 4px 8px; border-left: 2px solid var(--vscode-focusBorder); background: var(--vscode-editor-inactiveSelectionBackground); border-radius: 4px; }
 .act.task { font-weight: 600; margin-top: 6px; }
 .act.think { opacity: .7; font-style: italic; }
 .act.action { font-family: var(--vscode-editor-font-family); font-size: 11.5px; padding-left: 14px; }
 .act.result { opacity: .8; padding-left: 22px; font-size: 11.5px; }
 .act.done { color: var(--vscode-testing-iconPassed, #4c4); padding-left: 14px; }
 .act.fail, .act.result:has(+ .fail) { color: var(--vscode-testing-iconFailed, #e55); }
 .act.approval { color: var(--vscode-inputValidation-warningForeground, #db9); font-weight: 600; }
 .act.summary { font-weight: 600; font-size: 13px; margin-top: 8px; padding: 6px 8px; border-radius: 6px; background: var(--vscode-editor-selectionHighlightBackground); }
 #bottom { flex-shrink: 0; border-top: 1px solid var(--vscode-panel-border); padding: 8px 10px 10px; }
 .plan { border: 1px solid var(--vscode-panel-border); border-radius: 8px; padding: 8px 10px; margin-bottom: 8px; font-size: 12px; }
 .plan > b { display: block; margin-bottom: 4px; }
 .ptask { display: flex; justify-content: space-between; gap: 8px; padding: 3px 0; }
 .badge { font-size: 10.5px; opacity: .8; white-space: nowrap; }
 .approval { border: 1px solid var(--vscode-inputValidation-warningBorder);
   background: var(--vscode-inputValidation-warningBackground); border-radius: 8px; padding: 8px 10px; margin-bottom: 8px; }
 .approval button { margin-right: 6px; margin-top: 6px; }
 .composer { display: flex; gap: 6px; align-items: flex-end; }
 textarea { flex: 1; resize: none; min-height: 38px; max-height: 40vh; overflow-y: auto;
   background: var(--vscode-input-background); color: var(--vscode-input-foreground);
   border: 1px solid var(--vscode-input-border); border-radius: 8px; padding: 9px 10px;
   font: inherit; }
 textarea:focus { outline: 1px solid var(--vscode-focusBorder); }
 .go { background: var(--vscode-button-background); color: var(--vscode-button-foreground);
   border: none; padding: 9px 16px; border-radius: 8px; cursor: pointer; font-size: 13px; }
 .go:hover { background: var(--vscode-button-hoverBackground); }
 .go.stop { background: var(--vscode-inputValidation-errorBackground); }
 .hint { font-size: 10.5px; opacity: .55; margin-top: 5px; }
</style></head><body>
 <header>
   <span id="status" class="ok"><span class="dot"></span><span id="statustext">connecting…</span></span>
   <button class="iconbtn" id="expand" title="Open as an editor tab">⤢</button>
   <button class="iconbtn" id="clear" title="Clear conversation">⌫</button>
 </header>
 <div class="seg" id="seg">
   <button data-m="chat" class="on">Assisted</button>
   <button data-m="agent">Agent</button>
   <button data-m="computer">Computer</button>
   <button data-m="osdev">OS Dev</button>
   <button data-m="security">Security</button>
 </div>
 <div id="log"></div>
 <div id="bottom">
   <div id="plan"></div>
   <div id="approvals"></div>
   <div class="composer">
     <textarea id="in" rows="2" placeholder="Ask Vajra…"></textarea>
     <button class="go" id="go">Send</button>
     <button class="go stop" id="stop" style="display:none">Stop</button>
   </div>
   <div class="hint">Enter to send · Shift+Enter for a new line</div>
 </div>
<script>
 const vscode = acquireVsCodeApi();
 let mode = "chat", runId = null;
 const log = document.getElementById('log'), plan = document.getElementById('plan'),
   appr = document.getElementById('approvals'), input = document.getElementById('in');
 const grow = () => { input.style.height = 'auto'; input.style.height = Math.min(input.scrollHeight, window.innerHeight * 0.4) + 'px'; };
 input.addEventListener('input', grow);
 document.querySelectorAll('#seg button').forEach(b => b.onclick = () => {
   mode = b.dataset.m;
   document.querySelectorAll('#seg button').forEach(x => x.classList.toggle('on', x === b));
   input.placeholder = mode === 'chat' ? 'Ask Vajra…' : 'Describe the task…';
 });
 document.getElementById('expand').onclick = () => vscode.postMessage({ type: 'openTab' });
 document.getElementById('clear').onclick = () => { log.innerHTML = ''; vscode.postMessage({ type: 'clear' }); };
 function bubble(x) {
   const d = document.createElement('div');
   d.className = 'b ' + x.role;
   d.textContent = (x.role === 'tool' ? (x.ok ? '✓ ' : '✗ ') + 'inspected · ' : '') + x.text;
   log.appendChild(d); d.scrollIntoView({ block: 'end' });
 }
 const ICON = { goal:'🎯', info:'…', plan:'🗺️', task:'▸', think:'💭', action:'⚙️',
   result:'', done:'✓', fail:'⚠️', approval:'🔐', summary:'🏁' };
 function activity(a) {
   const d = document.createElement('div');
   d.className = 'act ' + a.kind;
   const ic = ICON[a.kind] === undefined ? '·' : ICON[a.kind];
   d.textContent = (ic ? ic + ' ' : '') + a.text;
   log.appendChild(d); d.scrollIntoView({ block: 'end' });
 }
 document.getElementById('go').onclick = () => {
   const t = input.value.trim(); if (!t) return;
   input.value = ''; grow();
   vscode.postMessage({ type: 'send', mode, text: t });
 };
 document.getElementById('stop').onclick = () => runId && vscode.postMessage({ type: 'stop', id: runId });
 input.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); document.getElementById('go').click(); } });
 window.addEventListener('message', e => {
   const m = e.data;
   if (m.type === 'health') {
     const s = document.getElementById('status');
     s.classList.toggle('ok', !!m.ok);
     document.getElementById('statustext').textContent = m.ok
       ? 'Vajra Core · ' + (m.models && m.models.primary ? m.models.primary : 'connected')
       : 'Core offline — ' + (m.error || 'start it with “Vajra: Start Core”');
   } else if (m.type === 'bubble') bubble(m.bubble);
   else if (m.type === 'activity') activity(m.item);
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
