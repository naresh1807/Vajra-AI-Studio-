/** Thin client for the Vajra Local API (manual v3.0 route map). Uses the extension host's global fetch. */
import * as vscode from "vscode";

export interface RunStatus {
  id: string;
  goal: string;
  status: string;
  progress: Record<string, number>;
  tasks: Array<Record<string, unknown>>;
  changed_files: string[];
}

export class VajraClient {
  private base(): string {
    return vscode.workspace.getConfiguration("vajra").get<string>("apiUrl", "http://127.0.0.1:8760");
  }
  private token(): string {
    return vscode.workspace.getConfiguration("vajra").get<string>("pairingToken", "");
  }
  private headers(): Record<string, string> {
    return { "Content-Type": "application/json", "X-Vajra-Token": this.token() };
  }

  async health(): Promise<{ status: string; models: Record<string, string> }> {
    const r = await fetch(`${this.base()}/api/health`);
    if (!r.ok) throw new Error(`Core not reachable (${r.status})`);
    return r.json() as Promise<{ status: string; models: Record<string, string> }>;
  }

  async chat(message: string): Promise<string> {
    const r = await fetch(`${this.base()}/api/agent/chat`, {
      method: "POST",
      headers: this.headers(),
      body: JSON.stringify({ message }),
    });
    if (!r.ok) throw new Error(await r.text());
    return ((await r.json()) as { reply: string }).reply;
  }

  async openProject(rootPath: string): Promise<{ id: string }> {
    const r = await fetch(`${this.base()}/api/projects`, {
      method: "POST",
      headers: this.headers(),
      body: JSON.stringify({ root_path: rootPath }),
    });
    if (!r.ok) throw new Error(await r.text());
    return r.json() as Promise<{ id: string }>;
  }

  async startRun(goal: string, workspaceRoot: string): Promise<RunStatus> {
    const r = await fetch(`${this.base()}/api/agent/run`, {
      method: "POST",
      headers: this.headers(),
      body: JSON.stringify({ goal, workspace_root: workspaceRoot, autostart: true }),
    });
    if (!r.ok) throw new Error(await r.text());
    return r.json() as Promise<RunStatus>;
  }

  async runStatus(runId: string): Promise<RunStatus> {
    const r = await fetch(`${this.base()}/api/agent/runs/${runId}`, { headers: this.headers() });
    if (!r.ok) throw new Error(await r.text());
    return r.json() as Promise<RunStatus>;
  }

  async stopRun(runId: string): Promise<void> {
    await fetch(`${this.base()}/api/agent/stop`, {
      method: "POST",
      headers: this.headers(),
      body: JSON.stringify({ run_id: runId }),
    });
  }

  async listApprovals(): Promise<Array<{ id: string; tool_name: string; reason: string }>> {
    const r = await fetch(`${this.base()}/api/approvals`, { headers: this.headers() });
    if (!r.ok) return [];
    return r.json() as Promise<Array<{ id: string; tool_name: string; reason: string }>>;
  }

  async resolveApproval(approvalId: string, verdict: "approved" | "rejected"): Promise<void> {
    await fetch(`${this.base()}/api/approvals`, {
      method: "POST",
      headers: this.headers(),
      body: JSON.stringify({ approval_id: approvalId, verdict }),
    });
  }
}
