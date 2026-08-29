import { useEffect, useRef, useState } from "react";
import type { Api, DebugState } from "./api";

export function DebugPanel({
  api,
  state,
  setState,
  onFrame,
}: {
  api: Api;
  state: DebugState | null;
  setState: (s: DebugState | null) => void;
  onFrame: (path: string, line: number) => void;
}) {
  const [expr, setExpr] = useState("");
  const [repl, setRepl] = useState<string[]>([]);
  const outRef = useRef<HTMLPreElement>(null);
  const id = state?.id;

  useEffect(() => {
    if (!id || state?.state === "terminated") return;
    const poll = async () => {
      try {
        const s = await api.debugState(id);
        setState(s);
        if (s.state === "stopped" && s.frames[0]) onFrame(s.frames[0].path, s.frames[0].line);
      } catch {
        /* ignore */
      }
    };
    const t = setInterval(poll, 700);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, state?.state]);

  useEffect(() => {
    outRef.current?.scrollTo(0, outRef.current.scrollHeight);
  }, [state?.output, repl]);

  if (!state) return <div className="muted pad">No debug session. Press ▷ Debug (F5) with a Python file open.</div>;

  const act = (a: "continue" | "next" | "step_in" | "step_out" | "pause") => id && api.debugAction(id, a);
  const running = state.state === "running";
  const stopped = state.state === "stopped";

  async function evaluate() {
    if (!expr.trim() || !id) return;
    const e = expr;
    setExpr("");
    setRepl((r) => [...r, `> ${e}`]);
    try {
      const res = await api.debugEvaluate(id, e);
      setRepl((r) => [...r, res.error ? `! ${res.error}` : `${res.result}`]);
    } catch (err) {
      setRepl((r) => [...r, `! ${err}`]);
    }
  }

  return (
    <div className="debug">
      <div className="dbg-toolbar">
        <span className={`badge ${state.state}`}>{state.state}</span>
        <button className="mini" disabled={!stopped} onClick={() => act("continue")} title="Continue (F5)">
          ▷
        </button>
        <button className="mini" disabled={!stopped} onClick={() => act("next")} title="Step Over (F10)">
          ⤼
        </button>
        <button className="mini" disabled={!stopped} onClick={() => act("step_in")} title="Step Into (F11)">
          ↳
        </button>
        <button className="mini" disabled={!stopped} onClick={() => act("step_out")} title="Step Out">
          ↰
        </button>
        <button className="mini" disabled={!running} onClick={() => act("pause")} title="Pause">
          ‖
        </button>
        <div className="spacer" />
        <button
          className="mini"
          onClick={async () => {
            if (id) await api.debugStop(id);
            setState(null);
          }}
        >
          ◼ Stop
        </button>
      </div>

      <div className="dbg-body">
        <div className="dbg-col">
          <div className="dbg-h">Call stack</div>
          {state.frames.map((f) => (
            <div key={f.id} className="dbg-frame" onClick={() => onFrame(f.path, f.line)}>
              {f.name} <span className="muted">:{f.line}</span>
            </div>
          ))}
          {!state.frames.length && <div className="muted pad">{running ? "running…" : "—"}</div>}
        </div>
        <div className="dbg-col">
          <div className="dbg-h">Variables</div>
          {(state.variables || []).map((v, i) => (
            <div key={i} className="dbg-var">
              <span className="vn">{v.name}</span>
              <span className="vv">{v.value}</span>
            </div>
          ))}
          {stopped && !state.variables?.length && <div className="muted pad">—</div>}
        </div>
        <div className="dbg-col dbg-console">
          <div className="dbg-h">Debug console</div>
          <pre ref={outRef} className="dbg-out">
            {state.output}
            {repl.length ? "\n" + repl.join("\n") : ""}
          </pre>
          <div className="dbg-eval">
            <span>›</span>
            <input
              value={expr}
              disabled={!stopped}
              placeholder={stopped ? "evaluate…" : "pause to evaluate"}
              onChange={(e) => setExpr(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && evaluate()}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
