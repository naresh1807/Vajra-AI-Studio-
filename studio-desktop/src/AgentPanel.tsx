import { useEffect, useRef, useState } from "react";
import type { Api, RunStatus } from "./api";

type Bubble =
  | { kind: "user" | "assistant" | "system"; text: string }
  | { kind: "tool"; text: string; ok: boolean };

export function AgentPanel({
  api,
  root,
  onFilesChanged,
}: {
  api: Api;
  root: string | null;
  onFilesChanged: () => void;
}) {
  const [mode, setMode] = useState<"chat" | "agent">("chat");
  const [bubbles, setBubbles] = useState<Bubble[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [run, setRun] = useState<RunStatus | null>(null);
  const [approvals, setApprovals] = useState<Array<{ id: string; tool_name: string; reason: string }>>([]);
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    end.current?.scrollIntoView();
  }, [bubbles, run]);

  useEffect(() => {
    if (!run || ["passed", "failed"].includes(run.status)) return;
    const t = setInterval(async () => {
      try {
        setRun(await api.runStatus(run.id));
        setApprovals(await api.approvals());
      } catch {
        /* ignore */
      }
    }, 1500);
    return () => clearInterval(t);
  }, [api, run]);

  useEffect(() => {
    if (run && ["passed", "failed"].includes(run.status)) {
      onFilesChanged();
      setBubbles((b) => [
        ...b,
        { kind: "system", text: `Run ${run.status}. Changed: ${run.changed_files.join(", ") || "none"}` },
      ]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [run?.status]);

  const history = () =>
    bubbles.filter((b) => b.kind === "user" || b.kind === "assistant").map((b) => ({
      role: b.kind as "user" | "assistant",
      content: (b as any).text,
    }));

  async function send() {
    const text = input.trim();
    if (!text || busy) return;
    setInput("");
    setBubbles((b) => [...b, { kind: "user", text }]);
    setBusy(true);
    try {
      if (mode === "chat") {
        const r = await api.chat(text, history(), root ?? undefined);
        for (const tc of r.tool_calls || []) setBubbles((b) => [...b, { kind: "tool", text: tc.tool, ok: tc.success }]);
        setBubbles((b) => [...b, { kind: "assistant", text: r.reply || "(no reply)" }]);
      } else {
        if (!root) {
          setBubbles((b) => [...b, { kind: "system", text: "Open a folder first." }]);
        } else {
          const s = await api.startRun(text, root);
          setRun(s);
          setBubbles((b) => [...b, { kind: "system", text: `Agent run started (${s.id.slice(0, 8)})` }]);
        }
      }
    } catch (e) {
      setBubbles((b) => [...b, { kind: "system", text: `Error: ${e}` }]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="agent">
      <div className="panel-head">
        <span>Vajra</span>
        <div className="seg">
          <button className={mode === "chat" ? "on" : ""} onClick={() => setMode("chat")}>
            Assisted
          </button>
          <button className={mode === "agent" ? "on" : ""} onClick={() => setMode("agent")}>
            Agent
          </button>
        </div>
      </div>

      <div className="agent-log">
        {bubbles.length === 0 && (
          <div className="muted pad">
            {mode === "chat"
              ? "Ask about the open workspace. Vajra can read your files."
              : "Describe a task. Vajra will plan → edit → test → review."}
          </div>
        )}
        {bubbles.map((b, i) =>
          b.kind === "tool" ? (
            <div key={i} className="b tool">
              {b.ok ? "✓" : "✗"} inspected · {b.text}
            </div>
          ) : (
            <div key={i} className={`b ${b.kind}`}>
              {b.kind !== "system" && <div className="who">{b.kind === "user" ? "You" : "Vajra"}</div>}
              <div className="tx">{(b as any).text}</div>
            </div>
          ),
        )}

        {run && (
          <div className="plan">
            <div className="plan-head">
              <b>Plan</b>
              <span className={`badge ${run.status}`}>{run.status}</span>
              {!["passed", "failed"].includes(run.status) && (
                <button className="mini" onClick={() => api.stopRun(run.id)}>
                  stop
                </button>
              )}
            </div>
            {run.tasks.map((t) => (
              <div key={t.id} className="ptask">
                <span>
                  {t.title} <span className="muted">· {t.agent}</span>
                </span>
                <span className={`badge ${t.state}`}>{t.state}</span>
              </div>
            ))}
          </div>
        )}

        {approvals.map((a) => (
          <div key={a.id} className="approval">
            <b>Approve {a.tool_name}?</b>
            <div className="muted">{a.reason}</div>
            <div className="row">
              <button className="mini on" onClick={() => api.resolveApproval(a.id, "approved")}>
                Approve
              </button>
              <button className="mini" onClick={() => api.resolveApproval(a.id, "rejected")}>
                Reject
              </button>
            </div>
          </div>
        ))}
        <div ref={end} />
      </div>

      <div className="agent-input">
        <textarea
          rows={2}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              void send();
            }
          }}
          placeholder={mode === "chat" ? "Ask Vajra…" : "Describe the task…"}
        />
        <button className="primary" disabled={busy || !input.trim()} onClick={send}>
          {mode === "chat" ? "Send" : "Run"}
        </button>
      </div>
    </div>
  );
}
