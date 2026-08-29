/** Vajra Local API client — manual v3.0 /api/* route map. */

const KEY = "vajra.studio.settings";

export interface Settings {
  apiUrl: string;
  pairingToken: string;
  lastWorkspace: string;
}

export function loadSettings(): Settings {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) return { lastWorkspace: "", ...(JSON.parse(raw) as Partial<Settings>) } as Settings;
  } catch {
    /* ignore */
  }
  return { apiUrl: "http://127.0.0.1:8760", pairingToken: "change-me-local-only", lastWorkspace: "" };
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

  openProject(rootPath: string) {
    return this.j<{ id: string; name: string; root_path: string; profile: any }>(`/api/projects`, {
      method: "POST",
      headers: this.h(),
      body: JSON.stringify({ root_path: rootPath }),
    });
  }

  tree(root: string) {
    return this.j<FileNode>(`/api/workspace/tree?root=${encodeURIComponent(root)}`, { headers: this.h(false) });
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

  gitStatus(root: string) {
    return this.j<{ stdout: string; stderr: string }>(`/api/git/status?root=${encodeURIComponent(root)}`, {
      headers: this.h(false),
    });
  }
  gitDiff(root: string, path?: string) {
    const q = path ? `&path=${encodeURIComponent(path)}` : "";
    return this.j<{ diff: string }>(`/api/git/diff?root=${encodeURIComponent(root)}${q}`, { headers: this.h(false) });
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
