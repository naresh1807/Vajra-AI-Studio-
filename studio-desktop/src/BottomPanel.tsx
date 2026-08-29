import { useEffect, useRef, useState } from "react";
import type { Api, DebugState } from "./api";
import { DebugPanel } from "./DebugPanel";
import { monaco } from "./monaco";

type Tab = "problems" | "terminal" | "output" | "services" | "debug";

interface Problem {
  path: string;
  line: number;
  column: number;
  severity: number;
  message: string;
}

export function BottomPanel({
  api,
  root,
  events,
  debug,
  setDebug,
  onDebugFrame,
  onOpenAt,
}: {
  api: Api;
  root: string | null;
  events: any[];
  debug: DebugState | null;
  setDebug: (s: DebugState | null) => void;
  onDebugFrame: (path: string, line: number) => void;
  onOpenAt: (path: string, line: number) => void;
}) {
  const [tab, setTab] = useState<Tab>("terminal");
  const [problems, setProblems] = useState<Problem[]>([]);

  useEffect(() => {
    const collect = () => {
      const markers = monaco.editor.getModelMarkers({ owner: "vajra-lsp" });
      setProblems(
        markers
          .map((m) => {
            const model = monaco.editor.getModels().find((x) => x.uri.toString() === m.resource.toString());
            const path = (model as any)?.__vajraPath as string | undefined;
            return path
              ? {
                  path,
                  line: m.startLineNumber,
                  column: m.startColumn,
                  severity: m.severity,
                  message: m.message,
                }
              : null;
          })
          .filter(Boolean) as Problem[],
      );
    };
    collect();
    const sub = monaco.editor.onDidChangeMarkers(collect);
    return () => sub.dispose();
  }, []);

  useEffect(() => {
    if (debug) setTab("debug");
  }, [debug?.id]);
  const [lines, setLines] = useState<string[]>([]);
  const [cmd, setCmd] = useState("");
  const [busy, setBusy] = useState(false);
  const [procs, setProcs] = useState<
    Array<{ id: string; label: string; running: boolean; url: string | null; exit_code: number | null }>
  >([]);
  const [svcCmd, setSvcCmd] = useState("");
  const termEnd = useRef<HTMLDivElement>(null);
  const outEnd = useRef<HTMLDivElement>(null);

  useEffect(() => {
    termEnd.current?.scrollIntoView();
  }, [lines]);
  useEffect(() => {
    outEnd.current?.scrollIntoView();
  }, [events, tab]);

  useEffect(() => {
    const poll = () => api.procList().then(setProcs);
    poll();
    const t = setInterval(poll, 2000);
    return () => clearInterval(t);
  }, [api]);

  async function run() {
    const c = cmd.trim();
    if (!c || !root || busy) return;
    setCmd("");
    setLines((l) => [...l, `$ ${c}`]);
    setBusy(true);
    try {
      const r = await api.terminalRun(root, c);
      const out = [r.stdout, r.stderr].filter(Boolean).join("\n").trimEnd();
      setLines((l) => [...l, ...(out ? out.split("\n") : []), `[exit ${r.exit_code} · ${r.duration_ms}ms]`]);
    } catch (e) {
      setLines((l) => [...l, `error: ${e}`]);
    } finally {
      setBusy(false);
    }
  }

  async function startService() {
    const c = svcCmd.trim();
    if (!c || !root) return;
    setSvcCmd("");
    try {
      await api.procStart(root, c);
      setProcs(await api.procList());
    } catch (e) {
      setLines((l) => [...l, `service error: ${e}`]);
    }
  }

  const running = procs.filter((p) => p.running);

  return (
    <div className="bottom">
      <div className="bottom-tabs">
        <button className={tab === "problems" ? "active" : ""} onClick={() => setTab("problems")}>
          Problems {problems.length ? `(${problems.length})` : ""}
        </button>
        <button className={tab === "terminal" ? "active" : ""} onClick={() => setTab("terminal")}>
          Terminal
        </button>
        <button className={tab === "output" ? "active" : ""} onClick={() => setTab("output")}>
          Output {events.length ? `(${events.length})` : ""}
        </button>
        <button className={tab === "services" ? "active" : ""} onClick={() => setTab("services")}>
          Services {running.length ? `(${running.length})` : ""}
        </button>
        <button className={tab === "debug" ? "active" : ""} onClick={() => setTab("debug")}>
          Debug {debug && debug.state !== "terminated" ? "●" : ""}
        </button>
      </div>

      {tab === "debug" && (
        <DebugPanel api={api} state={debug} setState={setDebug} onFrame={onDebugFrame} />
      )}

      {tab === "problems" && (
        <div className="problems">
          {problems.length === 0 && <div className="muted pad">No problems detected.</div>}
          {problems
            .sort((a, b) => a.path.localeCompare(b.path) || a.line - b.line)
            .map((p, i) => (
              <div key={i} className="prob-row" onClick={() => onOpenAt(p.path, p.line)}>
                <span className={`prob-sev s${p.severity}`}>
                  {p.severity === 8 ? "✕" : p.severity === 4 ? "▲" : "ⓘ"}
                </span>
                <span className="prob-msg">{p.message}</span>
                <span className="muted">{p.path.split("/").pop()}:{p.line}</span>
              </div>
            ))}
        </div>
      )}

      {tab === "terminal" && (
        <div className="term">
          <div className="term-scroll">
            {lines.map((l, i) => (
              <div key={i} className={l.startsWith("$ ") ? "cmd" : l.startsWith("[exit") ? "exit" : ""}>
                {l}
              </div>
            ))}
            <div ref={termEnd} />
          </div>
          <div className="term-input">
            <span>$</span>
            <input
              value={cmd}
              disabled={!root || busy}
              onChange={(e) => setCmd(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && run()}
              placeholder={root ? "run a command (waits for it to finish)…" : "open a folder first"}
            />
          </div>
        </div>
      )}

      {tab === "output" && (
        <div className="output">
          {events.slice(-300).map((e, i) => (
            <div key={i} className="ev">
              <span className="k">{e.kind}</span>
              <span className="p">{e.payload?.title || e.payload?.tool || e.payload?.note || ""}</span>
            </div>
          ))}
          <div ref={outEnd} />
        </div>
      )}

      {tab === "services" && (
        <div className="services">
          <div className="svc-start">
            <input
              value={svcCmd}
              disabled={!root}
              onChange={(e) => setSvcCmd(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && startService()}
              placeholder={root ? "start a dev server, e.g. npm run dev" : "open a folder first"}
            />
            <button onClick={startService} disabled={!root || !svcCmd.trim()}>
              Start
            </button>
          </div>
          {procs.length === 0 && <div className="muted pad">No background processes.</div>}
          {procs.map((p) => (
            <div key={p.id} className="svc-row">
              <span className={`dot ${p.running ? "ok" : "bad"}`} />
              <span className="svc-label">{p.label}</span>
              {p.url && (
                <a href={p.url} target="_blank" rel="noreferrer" className="svc-url">
                  {p.url}
                </a>
              )}
              {!p.running && <span className="muted small">exited {p.exit_code}</span>}
              <div className="spacer" />
              {p.running && (
                <button className="mini" onClick={() => api.procStop(p.id).then(() => api.procList().then(setProcs))}>
                  Stop
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
