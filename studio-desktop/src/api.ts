/** Vajra Local API client — manual v3.0 /api/* route map. */

const KEY = "vajra.studio.settings";

export interface Settings {
  apiUrl: string;
  pairingToken: string;
  lastWorkspace: string;
  inlineCompletions: boolean;
}

export function loadSettings(): Settings {
  const base: Settings = {
    apiUrl: "http://127.0.0.1:8760",
    pairingToken: "change-me-local-only",
    lastWorkspace: "",
    inlineCompletions: false,
  };
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) return { ...base, ...(JSON.parse(raw) as Partial<Settings>) };
  } catch {
    /* ignore */
  }
  return base;
}

export function saveSettings(s: Settings): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(s));
  } catch {
    /* ignore */
  }
}

export interface FileNode {
  name: string;
  path: string;
  type: "file" | "dir";
  size?: number;
  children?: FileNode[];
}

export interface DebugState {
  id: string;
  state: "starting" | "running" | "stopped" | "terminated";
  stopped_reason: string;
  program: string;
  frames: Array<{ id: number; name: string; path: string; line: number }>;
  output: string;
  variables?: Array<{ scope: string; name: string; value: string; type: string }>;
}

export interface RunStatus {
  id: string;
  goal: string;
  status: string;
  progress: Record<string, number>;
  tasks: Array<{ id: string; title: string; agent: string; state: string; result_summary?: string }>;
  changed_files: string[];
}

export class Api {
  constructor(private s: Settings) {}

  private h(json = true): Record<string, string> {
    const h: Record<string, string> = { "X-Vajra-Token": this.s.pairingToken };
    if (json) h["Content-Type"] = "application/json";
    return h;
  }
  private async j<T>(path: string, init?: RequestInit): Promise<T> {
    const r = await fetch(`${this.s.apiUrl}${path}`, init);
    if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
    return r.json() as Promise<T>;
  }

  health() {
    return this.j<{ status: string; version: string; models: Record<string, string> }>(`/api/health`);
  }

  fsList(path: string) {
    return this.j<{ path: string; parent: string | null; entries: Array<{ name: string; path: string }> }>(
      `/api/fs/list?path=${encodeURIComponent(path)}`,
      { headers: this.h(false) },
    );
  }
  fsMkdir(path: string) {
    return this.j<{ path: string }>(`/api/fs/mkdir`, {
      method: "POST",
      headers: this.h(),
      body: JSON.stringify({ root_path: path }),
    });
  }

  openProject(rootPath: string, create = false) {
    return this.j<{ id: string; name: string; root_path: string; profile: any }>(`/api/projects`, {
      method: "POST",
      headers: this.h(),
      body: JSON.stringify({ root_path: rootPath, create }),
    });
  }

  tree(root: string) {
    return this.j<FileNode>(`/api/workspace/tree?root=${encodeURIComponent(root)}`, { headers: this.h(false) });
  }

  search(root: string, query: string, opts: { is_regex?: boolean; case_sensitive?: boolean; glob?: string } = {}) {
    return this.j<{ hits: Array<{ path: string; line: number; text: string }>; truncated: boolean }>(
      `/api/workspace/search`,
      { method: "POST", headers: this.h(), body: JSON.stringify({ root, query, ...opts }) },
    );
  }

  readFile(root: string, path: string) {
    return this.j<{ path: string; content: string; bytes: number; truncated: boolean }>(`/api/files/read`, {
      method: "POST",
      headers: this.h(),
      body: JSON.stringify({ root, path }),
    });
  }

  writeFile(root: string, path: string, content: string) {
    return this.j<{ path: string; created: boolean; bytes: number; diff: string }>(`/api/files/write`, {
      method: "POST",
      headers: this.h(),
      body: JSON.stringify({ root, path, content }),
    });
  }

  terminalRun(root: string, command: string) {
    return this.j<{ stdout: string; stderr: string; exit_code: number | null; duration_ms: number; command: string[] }>(
      `/api/terminal/run`,
      { method: "POST", headers: this.h(), body: JSON.stringify({ root, command }) },
    );
  }

  // -- debugging --
  debugStart(root: string, program: string, breakpoints: Record<string, number[]>, args: string[] = []) {
    return this.j<DebugState>(`/api/debug/start`, {
      method: "POST",
      headers: this.h(),
      body: JSON.stringify({ root, program, args, breakpoints }),
    });
  }
  debugState(id: string) {
    return this.j<DebugState>(`/api/debug/state/${id}`, { headers: this.h(false) });
  }
  debugAction(id: string, action: "continue" | "next" | "step_in" | "step_out" | "pause") {
    return this.j(`/api/debug/action`, {
      method: "POST",
      headers: this.h(),
      body: JSON.stringify({ session_id: id, action }),
    });
  }
  debugBreakpoints(id: string, path: string, lines: number[]) {
    return this.j(`/api/debug/breakpoints`, {
      method: "POST",
      headers: this.h(),
      body: JSON.stringify({ session_id: id, path, lines }),
    });
  }
  debugEvaluate(id: string, expression: string) {
    return this.j<{ result: string | null; type: string | null; error: string | null }>(`/api/debug/evaluate`, {
      method: "POST",
      headers: this.h(),
      body: JSON.stringify({ session_id: id, expression }),
    });
  }
  debugStop(id: string) {
    return fetch(`${this.s.apiUrl}/api/debug/stop/${id}`, { method: "POST", headers: this.h() });
  }

  procList() {
    return this.j<
      Array<{ id: string; label: string; running: boolean; url: string | null; exit_code: number | null }>
    >(`/api/proc/list`, { headers: this.h(false) }).catch(() => []);
  }
  procStart(root: string, command: string, label?: string) {
    return this.j<{ id: string; running: boolean; url: string | null; output: string }>(`/api/proc/start`, {
      method: "POST",
      headers: this.h(),
      body: JSON.stringify({ root, command, label }),
    });
  }
  procOutput(id: string) {
    return this.j<{ output: string; running: boolean; url: string | null }>(`/api/proc/${id}/output`, {
      headers: this.h(false),
    });
  }
  procStop(id: string) {
    return fetch(`${this.s.apiUrl}/api/proc/stop`, {
      method: "POST",
      headers: this.h(),
      body: JSON.stringify({ process_id: id }),
    });
  }

  gitStatus(root: string) {
    return this.j<{
      is_repo: boolean;
      branch: string;
      ahead: number;
      behind: number;
      files: Array<{ path: string; staged: boolean; unstaged: boolean; status: string }>;
    }>(`/api/git/status?root=${encodeURIComponent(root)}`, { headers: this.h(false) });
  }
  gitDiff(root: string, path?: string, staged = false) {
    const q = `${path ? `&path=${encodeURIComponent(path)}` : ""}${staged ? "&staged=true" : ""}`;
    return this.j<{ diff: string }>(`/api/git/diff?root=${encodeURIComponent(root)}${q}`, { headers: this.h(false) });
  }
  private gitPost<T = { ok: boolean }>(path: string, body: object) {
    return this.j<T>(path, { method: "POST", headers: this.h(), body: JSON.stringify(body) });
  }
  gitStage(root: string, paths: string[]) {
    return this.gitPost(`/api/git/stage`, { root, paths });
  }
  gitUnstage(root: string, paths: string[]) {
    return this.gitPost(`/api/git/unstage`, { root, paths });
  }
  gitDiscard(root: string, path: string) {
    return this.gitPost(`/api/git/discard`, { root, path });
  }
  gitCommit(root: string, message: string) {
    return this.gitPost<{ ok: boolean; commit: string }>(`/api/git/commit`, { root, message });
  }
  gitCheckpoint(root: string, label: string) {
    return this.gitPost<{ tag: string }>(`/api/git/checkpoint`, { root, label });
  }
  gitCheckpoints(root: string) {
    return this.j<Array<{ tag: string; date: string; subject: string }>>(
      `/api/git/checkpoints?root=${encodeURIComponent(root)}`,
      { headers: this.h(false) },
    ).catch(() => []);
  }
  gitRestore(root: string, target: string) {
    return this.gitPost(`/api/git/restore`, { root, target });
  }

  assist(body: {
    root: string;
    path: string;
    action: string;
    selection?: string | null;
    instruction?: string | null;
    language?: string;
  }) {
    return this.j<{ kind: "prose" | "edit"; text: string; new_content: string | null; diff: string | null }>(
      `/api/assist`,
      { method: "POST", headers: this.h(), body: JSON.stringify(body) },
    );
  }

  formatDoc(b: { root: string; path: string; content: string; language: string }) {
    return this.j<{ formatted: string; changed: boolean }>(`/api/format`, {
      method: "POST",
      headers: this.h(),
      body: JSON.stringify(b),
    });
  }

  inlineComplete(b: { root: string; path: string; prefix: string; suffix: string; language: string }) {
    return this.j<{ text: string }>(`/api/assist/complete`, {
      method: "POST",
      headers: this.h(),
      body: JSON.stringify(b),
    }).catch(() => ({ text: "" }));
  }

  private lsp<T>(kind: string, body: object) {
    return this.j<T>(`/api/lsp/${kind}`, { method: "POST", headers: this.h(), body: JSON.stringify(body) });
  }
  lspSupport() {
    return this.j<{ languages: Record<string, boolean> }>(`/api/lsp/support`, { headers: this.h(false) }).catch(
      () => ({ languages: {} }),
    );
  }
  lspDiagnostics(b: { root: string; path: string; content: string; language: string }) {
    return this.lsp<{ supported: boolean; diagnostics: any[] }>("diagnostics", b);
  }
  lspCompletion(b: {
    root: string;
    path: string;
    content: string;
    language: string;
    line: number;
    character: number;
  }) {
    return this.lsp<{ items: any[] }>("completion", b);
  }
  lspHover(b: {
    root: string;
    path: string;
    content: string;
    language: string;
    line: number;
    character: number;
  }) {
    return this.lsp<{ value: string | null }>("hover", b);
  }
  lspDefinition(b: {
    root: string;
    path: string;
    content: string;
    language: string;
    line: number;
    character: number;
  }) {
    return this.lsp<{ locations: Array<{ path: string; range: any }> }>("definition", b);
  }

  chat(message: string, history: Array<{ role: string; content: string }>, workspaceRoot?: string) {
    return this.j<{ reply: string; tool_calls: Array<{ tool: string; success: boolean }>; model: any }>(
      `/api/agent/chat`,
      {
        method: "POST",
        headers: this.h(),
        body: JSON.stringify({ message, history: history.slice(-12), workspace_root: workspaceRoot ?? null }),
      },
    );
  }

  startRun(goal: string, workspaceRoot: string) {
    return this.j<RunStatus>(`/api/agent/run`, {
      method: "POST",
      headers: this.h(),
      body: JSON.stringify({ goal, workspace_root: workspaceRoot, autostart: true }),
    });
  }
  runStatus(id: string) {
    return this.j<RunStatus>(`/api/agent/runs/${id}`, { headers: this.h(false) });
  }
  stopRun(id: string) {
    return fetch(`${this.s.apiUrl}/api/agent/stop`, {
      method: "POST",
      headers: this.h(),
      body: JSON.stringify({ run_id: id }),
    });
  }

  computerRun(instruction: string) {
    return this.j<{ id: string; status: string }>(`/api/computer/run`, {
      method: "POST",
      headers: this.h(),
      body: JSON.stringify({ instruction }),
    });
  }
  computerRunStatus(id: string) {
    return this.j<{ id: string; status: string; reply: string; actions: Array<{ tool: string; success: boolean }> }>(
      `/api/computer/runs/${id}`,
      { headers: this.h(false) },
    );
  }

  osdevRun(instruction: string) {
    return this.j<{ id: string; status: string }>(`/api/osdev/run`, {
      method: "POST",
      headers: this.h(),
      body: JSON.stringify({ instruction }),
    });
  }
  osdevRunStatus(id: string) {
    return this.j<{ id: string; status: string; reply: string; actions: Array<{ tool: string; success: boolean }> }>(
      `/api/osdev/runs/${id}`,
      { headers: this.h(false) },
    );
  }
  osdevProviders() {
    return this.j<{ qemu: Record<string, boolean> }>(`/api/osdev/providers`, { headers: this.h(false) });
  }

  approvals() {
    return this.j<Array<{ id: string; tool_name: string; reason: string }>>(`/api/approvals`, {
      headers: this.h(false),
    }).catch(() => []);
  }
  resolveApproval(id: string, verdict: "approved" | "rejected") {
    return fetch(`${this.s.apiUrl}/api/approvals`, {
      method: "POST",
      headers: this.h(),
      body: JSON.stringify({ approval_id: id, verdict }),
    });
  }

  events(onEvent: (e: any) => void): WebSocket {
    const url = this.s.apiUrl.replace(/^http/, "ws") + `/ws/events?token=${encodeURIComponent(this.s.pairingToken)}`;
    const ws = new WebSocket(url);
    ws.onmessage = (m) => {
      try {
        onEvent(JSON.parse(m.data));
      } catch {
        /* ignore */
      }
    };
    return ws;
  }
}
