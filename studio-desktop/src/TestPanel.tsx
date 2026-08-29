import { useMemo, useState } from "react";
import type { Api } from "./api";

type Outcome = "none" | "running" | "passed" | "failed" | "error" | "skipped";

const ICON: Record<Outcome, string> = {
  none: "○", running: "◍", passed: "✓", failed: "✗", error: "✗", skipped: "–",
};

export function TestPanel({
  api,
  root,
  onOpen,
}: {
  api: Api;
  root: string | null;
  onOpen: (path: string, line: number) => void;
}) {
  const [ids, setIds] = useState<string[]>([]);
  const [framework, setFramework] = useState<string>("");
  const [outcomes, setOutcomes] = useState<Record<string, Outcome>>({});
  const [totals, setTotals] = useState<Record<string, number>>({});
  const [busy, setBusy] = useState(false);
  const [output, setOutput] = useState("");

  async function discover() {
    if (!root) return;
    setBusy(true);
    try {
      const r = await api.testDiscover(root);
      setFramework(r.framework);
      setIds(r.tests);
      setOutcomes({});
    } finally {
      setBusy(false);
    }
  }

  async function run(nodeIds?: string[]) {
    if (!root || busy) return;
    setBusy(true);
    const targets = nodeIds ?? ids;
    setOutcomes((o) => ({ ...o, ...Object.fromEntries(targets.map((t) => [t, "running" as Outcome])) }));
    try {
      const r = await api.testRun(root, nodeIds);
      setFramework(r.framework);
      setTotals(r.totals || {});
      setOutput(r.output || "");
      const next: Record<string, Outcome> = {};
      for (const c of r.cases || []) next[c.id] = c.outcome as Outcome;
      setOutcomes((o) => {
        const merged = { ...o };
        for (const t of targets) merged[t] = next[t] ?? (r.ok ? "passed" : "none");
        return { ...merged, ...next };
      });
      if ((r.cases || []).length === 0 && r.framework !== "pytest") setIds([]);
    } finally {
      setBusy(false);
    }
  }

  const byFile = useMemo(() => {
    const m: Record<string, string[]> = {};
    for (const id of ids) {
      const file = id.split("::")[0];
      (m[file] ??= []).push(id);
    }
    return m;
  }, [ids]);

  const summary = Object.entries(totals)
    .map(([k, v]) => `${v} ${k}`)
    .join(" · ");

  return (
    <div className="testpanel">
      <div className="test-head">
        <button className="mini" disabled={!root || busy} onClick={discover}>
          {busy && !ids.length ? "…" : "Discover"}
        </button>
        <button className="mini" disabled={!root || busy || !ids.length} onClick={() => run()}>
          Run all
        </button>
        <span className="muted small">
          {framework ? `${framework}` : ""} {summary ? `— ${summary}` : ids.length ? `— ${ids.length} tests` : ""}
        </span>
      </div>
      <div className="test-tree">
        {!root && <div className="muted pad">Open a folder.</div>}
        {root && !ids.length && !busy && (
          <div className="muted pad">No tests discovered yet — hit Discover (pytest / npm test).</div>
        )}
        {Object.entries(byFile).map(([file, group]) => (
          <div key={file}>
            <div className="test-file">{file}</div>
            {group.map((id) => {
              const oc = outcomes[id] ?? "none";
              return (
                <div
                  key={id}
                  className={`test-row oc-${oc}`}
                  onClick={() => onOpen(file, 1)}
                >
                  <span className="test-ic">{ICON[oc]}</span>
                  <span className="test-name">{id.split("::").slice(1).join(" › ")}</span>
                  <button
                    className="mini ghost"
                    title="Run this test"
                    onClick={(e) => {
                      e.stopPropagation();
                      void run([id]);
                    }}
                  >
                    ▶
                  </button>
                </div>
              );
            })}
          </div>
        ))}
      </div>
      {output && (
        <pre className="test-output">{output.slice(-6000)}</pre>
      )}
    </div>
  );
}
