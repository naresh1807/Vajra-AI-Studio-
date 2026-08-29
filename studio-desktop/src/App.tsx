import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as api from "./api";
import type { ChatMsg, Settings } from "./api";

type Screen = "dashboard" | "chat" | "projects" | "tasks" | "approvals" | "logs" | "settings";

export function App() {
  const [screen, setScreen] = useState<Screen>("chat");
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
    ["chat", "Chat"],
    ["dashboard", "Dashboard"],
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
        {screen === "chat" && (
          <Chat
            settings={settings}
            onGoal={(id) => { setGoalId(id); setScreen("tasks"); }}
          />
        )}
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

type Bubble =
  | { kind: "user"; text: string }
  | { kind: "assistant"; text: string; model?: string }
  | { kind: "tool"; text: string; ok: boolean }
  | { kind: "system"; text: string };

const WS_KEY = "vajra.chat.workspace";

function Chat({ settings, onGoal }: { settings: Settings; onGoal: (id: string) => void }) {
  const [bubbles, setBubbles] = useState<Bubble[]>([]);
  const [input, setInput] = useState("");
  const [root, setRoot] = useState(() => {
    try { return localStorage.getItem(WS_KEY) || ""; } catch { return ""; }
  });
  const [busy, setBusy] = useState(false);
  const scroller = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" });
  }, [bubbles, busy]);

  useEffect(() => {
    try { localStorage.setItem(WS_KEY, root); } catch { /* ignore */ }
  }, [root]);

  const history = (): ChatMsg[] =>
    bubbles
      .filter((b) => b.kind === "user" || b.kind === "assistant")
      .map((b) => ({ role: b.kind as "user" | "assistant", content: (b as any).text }));

  async function send() {
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    setBubbles((b) => [...b, { kind: "user", text }]);
    setBusy(true);
    try {
      const res = await api.chat(settings, text, history(), root || undefined);
      for (const tc of res.tool_calls || []) {
        setBubbles((b) => [...b, { kind: "tool", text: `${tc.tool}`, ok: tc.success }]);
      }
      const modelLabel = res.model?.provider ? `${res.model.provider}:${res.model.model}` : "";
      setBubbles((b) => [...b, { kind: "assistant", text: res.reply || "(no reply)", model: modelLabel }]);
    } catch (e) {
      setBubbles((b) => [...b, { kind: "system", text: `Error: ${e}` }]);
    } finally {
      setBusy(false);
    }
  }

  async function build() {
    if (!root) {
      setBubbles((b) => [...b, { kind: "system", text: "Set a workspace folder first (field above)." }]);
      return;
    }
    // Turn the conversation so far into an autonomous goal.
    const convo = bubbles
      .filter((b) => b.kind === "user" || b.kind === "assistant")
      .map((b) => `${b.kind}: ${(b as any).text}`)
      .join("\n");
    const goalText = input.trim() || convo || "Implement what we just discussed.";
    setBusy(true);
    try {
      await api.openProject(settings, root);
      const g = await api.createGoal(settings, goalText, root);
      setBubbles((b) => [...b, { kind: "system", text: `Autonomous task started (${g.id}). Opening Task Graph…` }]);
      setInput("");
      onGoal(g.id);
    } catch (e) {
      setBubbles((b) => [...b, { kind: "system", text: `Error: ${e}` }]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="chat">
      <div className="chat-head">
        <h1 style={{ margin: 0 }}>Chat</h1>
        <input
          className="ws"
          value={root}
          onChange={(e) => setRoot(e.target.value)}
          placeholder="workspace folder — E:\path\to\project (lets Vajra read your code)"
        />
      </div>

      <div className="chat-log" ref={scroller}>
        {bubbles.length === 0 && (
          <div className="muted" style={{ padding: 20 }}>
            Ask about your code, or describe a change and hit <b>Build it</b> to run the
            autonomous plan → code → test → review loop.
          </div>
        )}
        {bubbles.map((b, i) => (
          <div key={i} className={`bubble ${b.kind}`}>
            {b.kind === "tool" ? (
              <span className="muted">
                {b.ok ? "✓" : "✗"} inspected · {b.text}
              </span>
            ) : (
              <>
                <div className="who">{b.kind === "user" ? "You" : b.kind === "assistant" ? "Vajra" : "•"}</div>
                <div className="text">{(b as any).text}</div>
                {b.kind === "assistant" && (b as any).model && (
                  <div className="model muted">{(b as any).model}</div>
                )}
              </>
            )}
          </div>
        ))}
        {busy && <div className="bubble assistant"><div className="who">Vajra</div><div className="text">…</div></div>}
      </div>

      <div className="chat-input">
        <textarea
          rows={2}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void send(); }
          }}
          placeholder="Message Vajra…  (Enter to send, Shift+Enter for newline)"
        />
        <div className="row" style={{ marginTop: 6 }}>
          <button className="primary" disabled={busy || !input.trim()} onClick={send}>Send</button>
          <button className="ghost" disabled={busy} onClick={build}>Build it ▶</button>
        </div>
      </div>
    </div>
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
