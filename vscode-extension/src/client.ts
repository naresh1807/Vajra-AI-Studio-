/** Client for the Vajra Local API (manual v3.0). Uses the extension host's global fetch. */
import * as vscode from "vscode";

export interface Health {
  status: string;
  models: Record<string, string>;
}
export interface RunStatus {
  id: string;
  goal?: string;
  status: string;
  progress?: Record<string, number>;
  tasks: Array<{ id: string; title: string; agent: string; state: string }>;
  changed_files: string[];
}
export interface Approval {
  id: string;
  tool_name: string;
  reason: string;
  arguments?: Record<string, unknown>;
}
export interface AssistResult {
  kind: string;
  text: string;
  new_content: string | null;
  diff: string | null;
}
export interface RagHit {
  ref: string;
  path: string;
  start_line: number;
  end_line: number;
  score: number;
  text: string;
}
export interface RunRef {
  id: string;
  status: string;
  reply?: string;
  actions?: Array<{ tool: string; success: boolean }>;
}

export class VajraClient {
  private tokenOverride = "";
  /** Set by CoreManager when it auto-starts a same-machine Core (reads data/device.json). */
  setToken(t: string) {
    this.tokenOverride = t || "";
  }
  private cfg() {
    return vscode.workspace.getConfiguration("vajra");
  }
  base(): string {
    return this.cfg().get<string>("apiUrl", "http://127.0.0.1:8760").replace(/\/$/, "");
  }
  private token(): string {
    return this.cfg().get<string>("pairingToken", "") || this.tokenOverride;
  }
  private h(): Record<string, string> {
    return { "Content-Type": "application/json", "X-Vajra-Token": this.token() };
  }
  private async j<T>(path: string, init?: RequestInit): Promise<T> {
    const r = await fetch(`${this.base()}${path}`, { headers: this.h(), ...init });
    if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
    return (await r.json()) as T;
  }

  health = () => this.j<Health>("/api/health", { headers: {} });
  ping = () => this.j<{ detail: string }>("/api/ping");
  models = () =>
    this.j<{
      models: Record<string, string>;
      primary: { requests: number; failures: number; avg_latency_ms: number; circuit: string };
      fallback: { requests: number; failures: number; circuit: string };
    }>("/api/models");
  doctor = () =>
    this.j<{ ok: boolean; checks: Array<{ name: string; status: string; detail: string; required: boolean }> }>(
      "/api/setup/health",
    );
  setupState = () =>
    this.j<{ completed: boolean; workspace?: string; device_id: string; paired_devices: number }>(
      "/api/setup/state",
    );
  setupComplete = (workspace?: string) =>
    this.j<{ ok: boolean }>("/api/setup/complete", {
      method: "POST",
      body: JSON.stringify({ workspace }),
    });

  openProject = (rootPath: string) =>
    this.j<{ id: string }>("/api/projects", {
      method: "POST",
      body: JSON.stringify({ root_path: rootPath }),
    });

  chat = (message: string, history: Array<{ role: string; content: string }> = [], root?: string) =>
    this.j<{ reply: string; tool_calls: Array<{ tool: string; success: boolean }> }>("/api/agent/chat", {
      method: "POST",
      body: JSON.stringify({ message, history, workspace_root: root }),
    });

  startRun = (goal: string, root: string, focus = "") =>
    this.j<RunStatus>("/api/agent/run", {
      method: "POST",
      body: JSON.stringify({ goal, workspace_root: root, autostart: true, focus }),
    });
  runStatus = (id: string) => this.j<RunStatus>(`/api/agent/runs/${id}`);
  stopRun = (id: string) =>
    this.j<unknown>("/api/agent/stop", { method: "POST", body: JSON.stringify({ run_id: id }) });
  interrupted = () =>
    this.j<{ interrupted: Array<{ id: string; goal: string; changed_files: string[] }> }>(
      "/api/agent/interrupted",
    ).catch(() => ({ interrupted: [] }));

  gitRollback = (root: string, target: string) =>
    this.j<unknown>("/api/git/rollback", {
      method: "POST",
      body: JSON.stringify({ root, target }),
    });

  approvals = () => this.j<Approval[]>("/api/approvals").catch(() => [] as Approval[]);
  resolveApproval = (id: string, verdict: "approved" | "rejected") =>
    this.j<unknown>("/api/approvals", {
      method: "POST",
      body: JSON.stringify({ approval_id: id, verdict }),
    });

  assist = (root: string, path: string, content: string, action: string, selection: string, instruction?: string) =>
    this.j<AssistResult>("/api/assist", {
      method: "POST",
      body: JSON.stringify({ root, path, content, action, selection, instruction }),
    });

  complete = (root: string, path: string, prefix: string, suffix: string, language: string) =>
    this.j<{ text: string }>("/api/assist/complete", {
      method: "POST",
      body: JSON.stringify({ root, path, prefix, suffix, language }),
    });

  ragReindex = (root: string) =>
    this.j<{ files: number; chunks: number; embedder: string }>("/api/rag/reindex", {
      method: "POST",
      body: JSON.stringify({ root }),
    });
  ragSearch = (root: string, query: string, k = 12) =>
    this.j<{ hits: RagHit[] }>("/api/rag/search", {
      method: "POST",
      body: JSON.stringify({ root, query, k }),
    });

  testDiscover = (root: string) =>
    this.j<{ framework: string; tests: string[] }>("/api/testing/discover", {
      method: "POST",
      body: JSON.stringify({ root }),
    });
  testRun = (root: string, nodeIds?: string[]) =>
    this.j<{
      framework: string;
      ok: boolean;
      cases: Array<{ id: string; outcome: string }>;
      totals: Record<string, number>;
      output: string;
    }>("/api/testing/run", { method: "POST", body: JSON.stringify({ root, node_ids: nodeIds ?? [] }) });

  gitStatus = (root: string) =>
    this.j<{ branch: string; files: Array<{ path: string; status: string; staged: boolean }> }>(
      `/api/git/status?root=${encodeURIComponent(root)}`,
    );

  runPlan = (root: string, kind = "run") =>
    this.j<{
      command: string;
      framework: string | null;
      port: number | null;
      kind: string;
      alternatives: Record<string, string>;
    }>(`/api/run/plan?root=${encodeURIComponent(root)}&kind=${kind}`);
  runStart = (root: string, kind = "run", command?: string) =>
    this.j<{ kind: string; command: string; url?: string | null; exit_code?: number; stdout?: string }>(
      "/api/run/start",
      { method: "POST", body: JSON.stringify({ root, kind, command }) },
    );
  gitCheckpoint = (root: string, label: string) =>
    this.j<unknown>("/api/git/checkpoint", { method: "POST", body: JSON.stringify({ root, label }) });
  gitCheckpoints = (root: string) =>
    this.j<Array<{ ref: string; label: string; created_at?: number }>>(
      `/api/git/checkpoints?root=${encodeURIComponent(root)}`,
    );

  computerRun = (instruction: string) =>
    this.j<{ id: string }>("/api/computer/run", { method: "POST", body: JSON.stringify({ instruction }) });
  computerRunStatus = (id: string) => this.j<RunRef>(`/api/computer/runs/${id}`);

  osdevRun = (instruction: string) =>
    this.j<{ id: string }>("/api/osdev/run", { method: "POST", body: JSON.stringify({ instruction }) });
  osdevRunStatus = (id: string) => this.j<RunRef>(`/api/osdev/runs/${id}`);

  securityRun = (instruction: string, root: string) =>
    this.j<{ id: string }>("/api/security/run", {
      method: "POST",
      body: JSON.stringify({ instruction, root }),
    });
  securityRunStatus = (id: string) => this.j<RunRef>(`/api/security/runs/${id}`);
}
