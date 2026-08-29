import { useEffect, useRef, useState } from "react";
import type { Api } from "./api";

type Tab = "terminal" | "output";

export function BottomPanel({
  api,
  root,
  events,
}: {
  api: Api;
  root: string | null;
  events: any[];
}) {
  const [tab, setTab] = useState<Tab>("terminal");
  const [lines, setLines] = useState<string[]>([]);
  const [cmd, setCmd] = useState("");
  const [busy, setBusy] = useState(false);
  const termEnd = useRef<HTMLDivElement>(null);
  const outEnd = useRef<HTMLDivElement>(null);

  useEffect(() => {
    termEnd.current?.scrollIntoView();
  }, [lines]);
  useEffect(() => {
    outEnd.current?.scrollIntoView();
  }, [events, tab]);

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

  return (
    <div className="bottom">
      <div className="bottom-tabs">
        <button className={tab === "terminal" ? "active" : ""} onClick={() => setTab("terminal")}>
          Terminal
        </button>
        <button className={tab === "output" ? "active" : ""} onClick={() => setTab("output")}>
          Output {events.length ? `(${events.length})` : ""}
        </button>
      </div>

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
              placeholder={root ? "run a command…" : "open a folder first"}
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
    </div>
  );
}
