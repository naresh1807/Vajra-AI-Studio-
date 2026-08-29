/** Vajra Local API client for the desktop shell. */

const KEY = "vajra.settings";

export interface Settings {
  apiUrl: string;
  pairingToken: string;
}

export function loadSettings(): Settings {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw) return JSON.parse(raw) as Settings;
  } catch {
    /* ignore */
  }
  return { apiUrl: "http://127.0.0.1:8760", pairingToken: "change-me-local-only" };
}

export function saveSettings(s: Settings): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(s));
  } catch {
    /* ignore */
  }
}

function headers(s: Settings): Record<string, string> {
  return { "Content-Type": "application/json", "X-Vajra-Token": s.pairingToken };
}

export async function health(s: Settings) {
  const r = await fetch(`${s.apiUrl}/health`);
  if (!r.ok) throw new Error(`Core unreachable (${r.status})`);
  return r.json() as Promise<{ status: string; version: string; models: Record<string, string> }>;
}

export async function listProjects(s: Settings) {
  const r = await fetch(`${s.apiUrl}/api/v1/projects`, { headers: headers(s) });
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<Array<{ id: string; name: string; root_path: string }>>;
}

export async function openProject(s: Settings, rootPath: string) {
  const r = await fetch(`${s.apiUrl}/api/v1/projects/open`, {
    method: "POST",
    headers: headers(s),
    body: JSON.stringify({ root_path: rootPath }),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<{ id: string; name: string; root_path: string; profile: any }>;
}

export async function createGoal(s: Settings, text: string, workspaceRoot: string) {
  const r = await fetch(`${s.apiUrl}/api/v1/goals`, {
    method: "POST",
    headers: headers(s),
    body: JSON.stringify({ text, workspace_root: workspaceRoot, autostart: true }),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<{ id: string }>;
}

export async function goalStatus(s: Settings, goalId: string) {
  const r = await fetch(`${s.apiUrl}/api/v1/goals/${goalId}`, { headers: headers(s) });
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<{
    id: string;
    text: string;
    status: string;
    progress: Record<string, number>;
    tasks: Array<{ id: string; title: string; agent: string; state: string }>;
    changed_files: string[];
  }>;
}

export async function cancelGoal(s: Settings, goalId: string) {
  await fetch(`${s.apiUrl}/api/v1/tasks/${goalId}/cancel`, { method: "POST", headers: headers(s) });
}

export async function listApprovals(s: Settings) {
  const r = await fetch(`${s.apiUrl}/api/v1/approvals`, { headers: headers(s) });
  if (!r.ok) return [];
  return r.json() as Promise<Array<{ id: string; tool_name: string; reason: string; goal_id: string }>>;
}

export async function resolveApproval(s: Settings, id: string, verdict: "approved" | "rejected") {
  await fetch(`${s.apiUrl}/api/v1/tools/approve`, {
    method: "POST",
    headers: headers(s),
    body: JSON.stringify({ approval_id: id, verdict }),
  });
}

export function eventSocket(s: Settings): WebSocket {
  const url = s.apiUrl.replace(/^http/, "ws") + `/api/v1/events?token=${encodeURIComponent(s.pairingToken)}`;
  return new WebSocket(url);
}
