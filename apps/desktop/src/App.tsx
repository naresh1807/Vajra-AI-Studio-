import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as api from "./api";
import type { Settings } from "./api";

type Screen = "dashboard" | "chat" | "projects" | "tasks" | "approvals" | "logs" | "settings";

export function App() {
  const [screen, setScreen] = useState<Screen>("dashboard");
  const [settings, setSettings] = useState<Settings>(api.loadSettings());
  const [core, setCore] = useState<{ ok: boolean; text: string }>({ ok: false, text: "checking…" });
  const [events, setEvents] = useState<any[]>([]);
  const [goalId, setGoalId] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  const refreshHealth = useCallback(async () => {
    try {
      const h = await api.health(settings);
      setCore({ ok: true, text: `Vajra Core ${h.version} · ${JSON.stringify(h.models)}` });
    } catch (e) {
      setCore({ ok: false, text: String(e) });
    }
  }, [settings]);

  useEffect(() => {
    void refreshHealth();
    const t = setInterval(refreshHealth, 5000);
    return () => clearInterval(t);
  }, [refreshHealth]);

  useEffect(() => {
    try {
      const ws = api.eventSocket(settings);
      ws.onmessage = (m) => setEvents((prev) => [...prev.slice(-400), JSON.parse(m.data)]);
      wsRef.current = ws;
      return () => ws.close();
    } catch {
      return;
    }
  }, [settings]);

  const nav: [Screen, string][] = [
    ["dashboard", "Dashboard"],
    ["chat", "Chat / Goal"],
    ["projects", "Projects"],
    ["tasks", "Task Graph"],
    ["approvals", "Approvals"],
    ["logs", "Logs"],
    ["settings", "Settings"],
  ];

  return (
    <div className="app">
      <aside className="side">
        <div className="brand">⚡ VAJRA AI</div>
        <nav className="nav">
          {nav.map(([id, label]) => (
            <button key={id} className={screen === id ? "active" : ""} onClick={() => setScreen(id)}>
              {label}
            </button>
          ))}
        </nav>
        <div style={{ marginTop: 16, padding: 8 }} className="row">
          <span className={`dot ${core.ok ? "ok" : "bad"}`} />
          <span className="muted" style={{ fontSize: 11 }}>{core.ok ? "Core online" : "Core offline"}</span>
        </div>
      </aside>

      <main className="main">
        {screen === "dashboard" && <Dashboard core={core} events={events} />}
        {screen === "chat" && <ChatGoal settings={settings} onGoal={(id) => { setGoalId(id); setScreen("tasks"); }} />}
        {screen === "projects" && <Projects settings={settings} />}
        {screen === "tasks" && <Tasks settings={settings} goalId={goalId} />}
        {screen === "approvals" && <Approvals settings={settings} />}
        {screen === "logs" && <Logs events={events} />}
        {screen === "settings" && (
          <SettingsScreen
            settings={settings}
            onSave={(s) => { api.saveSettings(s); setSettings(s); void refreshHealth(); }}
          />
        )}
      </main>
    </div>
  );
}

function Dashboard({ core, events }: { core: { ok: boolean; text: string }; events: any[] }) {
  const recent = events.slice(-8).reverse();
  return (
    <>
      <h1>Dashboard</h1>
      <div className="card">
        <div className="row"><span className={`dot ${core.ok ? "ok" : "bad"}`} /> <b>{core.text}</b></div>
        <p className="muted">The Desktop App is the primary execution host. Start the Core with <code>vajra-api</code>.</p>
      </div>
      <div className="card">
        <b>Recent activity</b>
        {recent.length === 0 && <p className="muted">No events yet.</p>}
        {recent.map((e, i) => (
          <div key={i} className="task">
            <span>{e.kind}</span>
            <span className="muted">{e.payload?.title || e.payload?.tool || ""}</span>
          </div>
        ))}
      </div>
    </>
  );
}

function ChatGoal({ settings, onGoal }: { settings: Settings; onGoal: (id: string) => void }) {
  const [text, setText] = useState("");
  const [root, setRoot] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  async function run() {
    setBusy(true); setErr("");
    try {
      await api.openProject(settings, root);
      const g = await api.createGoal(settings, text, root);
      onGoal(g.id);
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <h1>Chat / Goal</h1>
      <div className="card">
        <label className="muted">Workspace folder (absolute path)</label>
        <input value={root} onChange={(e) => setRoot(e.target.value)} placeholder="E:\path\to\project" />
        <label className="muted" style={{ marginTop: 10, display: "block" }}>Goal</label>
        <textarea rows={4} value={text} onChange={(e) => setText(e.target.value)}
          placeholder="e.g. Add a /students API endpoint and a React form, run tests." />
        <div className="row" style={{ marginTop: 10 }}>
          <button className="primary" disabled={busy || !text || !root} onClick={run}>
            {busy ? "Starting…" : "Run autonomously"}
          </button>
          {err && <span style={{ color: "var(--bad)" }}>{err}</span>}
        </div>
      </div>
    </>
  );
}

function Projects({ settings }: { settings: Settings }) {
  const [list, setList] = useState<Array<{ id: string; name: string; root_path: string }>>([]);
  const [root, setRoot] = useState("");
  const load = useCallback(() => { api.listProjects(settings).then(setList).catch(() => {}); }, [settings]);
  useEffect(load, [load]);
  return (
    <>
      <h1>Projects</h1>
      <div className="card">
        <div className="row">
          <input value={root} onChange={(e) => setRoot(e.target.value)} placeholder="Absolute path to a project folder" />
          <button className="ghost" onClick={async () => { await api.openProject(settings, root); setRoot(""); load(); }}>Open</button>
        </div>
      </div>
      {list.map((p) => (
        <div key={p.id} className="card">
          <b>{p.name}</b>
          <div className="muted" style={{ fontSize: 12 }}>{p.root_path}</div>
        </div>
      ))}
      {list.length === 0 && <p className="muted">No projects registered yet.</p>}
    </>
  );
}

function Tasks({ settings, goalId }: { settings: Settings; goalId: string | null }) {
  const [status, setStatus] = useState<any>(null);
  useEffect(() => {
    if (!goalId) return;
    const poll = () => api.goalStatus(settings, goalId).then(setStatus).catch(() => {});
    poll();
    const t = setInterval(poll, 1500);
    return () => clearInterval(t);
  }, [settings, goalId]);

  if (!goalId) return (<><h1>Task Graph</h1><p className="muted">Start a goal from Chat / Goal.</p></>);
  return (
    <>
      <h1>Task Graph</h1>
      <div className="card">
        <div className="row" style={{ justifyContent: "space-between" }}>
          <b>{status?.text || goalId}</b>
          <span className={`badge ${status?.status}`}>{status?.status || "…"}</span>
        </div>
        <div className="row" style={{ marginTop: 8 }}>
          <button className="ghost" onClick={() => api.cancelGoal(settings, goalId)}>Stop task</button>
        </div>
      </div>
      <div className="card">
        {(status?.tasks || []).map((t: any) => (
          <div key={t.id} className="task">
            <span>{t.title} <span className="muted">· {t.agent}</span></span>
            <span className={`badge ${t.state}`}>{t.state}</span>
          </div>
        ))}
      </div>
      {status?.changed_files?.length > 0 && (
        <div className="card">
          <b>Changed files</b>
          {status.changed_files.map((f: string) => <div key={f} className="muted" style={{ fontSize: 12 }}>{f}</div>)}
        </div>
      )}
    </>
  );
}

function Approvals({ settings }: { settings: Settings }) {
  const [list, setList] = useState<Array<{ id: string; tool_name: string; reason: string }>>([]);
  useEffect(() => {
    const poll = () => api.listApprovals(settings).then(setList).catch(() => {});
    poll();
    const t = setInterval(poll, 1500);
    return () => clearInterval(t);
  }, [settings]);
  return (
    <>
      <h1>Approvals</h1>
      {list.length === 0 && <p className="muted">Nothing waiting for approval.</p>}
      {list.map((a) => (
        <div key={a.id} className="card">
          <b>{a.tool_name}</b>
          <p className="muted">{a.reason}</p>
          <div className="row">
            <button className="primary" onClick={() => api.resolveApproval(settings, a.id, "approved")}>Approve</button>
            <button className="ghost" onClick={() => api.resolveApproval(settings, a.id, "rejected")}>Reject</button>
          </div>
        </div>
      ))}
    </>
  );
}

function Logs({ events }: { events: any[] }) {
  const text = useMemo(() => events.map((e) => JSON.stringify(e)).join("\n"), [events]);
  return (
    <>
      <h1>Logs</h1>
      <pre className="log">{text || "waiting for events…"}</pre>
    </>
  );
}

function SettingsScreen({ settings, onSave }: { settings: Settings; onSave: (s: Settings) => void }) {
  const [draft, setDraft] = useState(settings);
  return (
    <>
      <h1>Settings</h1>
      <div className="card">
        <label className="muted">Vajra Local API URL</label>
        <input value={draft.apiUrl} onChange={(e) => setDraft({ ...draft, apiUrl: e.target.value })} />
        <label className="muted" style={{ marginTop: 10, display: "block" }}>Pairing token</label>
        <input value={draft.pairingToken} onChange={(e) => setDraft({ ...draft, pairingToken: e.target.value })} />
        <div style={{ marginTop: 12 }}>
          <button className="primary" onClick={() => onSave(draft)}>Save</button>
        </div>
      </div>
    </>
  );
}
