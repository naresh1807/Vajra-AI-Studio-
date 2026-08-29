import { useState } from "react";
import type { Api } from "./api";

export function SearchPanel({
  api,
  root,
  onOpen,
}: {
  api: Api;
  root: string | null;
  onOpen: (path: string, line: number) => void;
}) {
  const [q, setQ] = useState("");
  const [glob, setGlob] = useState("*");
  const [regex, setRegex] = useState(false);
  const [hits, setHits] = useState<Array<{ path: string; line: number; text: string }>>([]);
  const [truncated, setTruncated] = useState(false);
  const [busy, setBusy] = useState(false);

  async function run() {
    if (!q.trim() || !root) return;
    setBusy(true);
    try {
      const r = await api.search(root, q, { is_regex: regex, glob: glob || "*" });
      setHits(r.hits);
      setTruncated(r.truncated);
    } catch {
      setHits([]);
    } finally {
      setBusy(false);
    }
  }

  const byFile = hits.reduce<Record<string, typeof hits>>((acc, h) => {
    (acc[h.path] ??= []).push(h);
    return acc;
  }, {});

  return (
    <div className="searchpanel">
      <div className="search-head">
        <input
          autoFocus
          placeholder="Search workspace"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && run()}
        />
        <div className="row" style={{ marginTop: 6 }}>
          <input className="glob" placeholder="files: *  or  *.py" value={glob} onChange={(e) => setGlob(e.target.value)} />
          <button className={`mini ${regex ? "on" : ""}`} title="Regex" onClick={() => setRegex((v) => !v)}>
            .*
          </button>
          <button className="mini" disabled={busy || !q.trim()} onClick={run}>
            {busy ? "…" : "Go"}
          </button>
        </div>
      </div>
      <div className="search-results">
        {!root && <div className="muted pad">Open a folder.</div>}
        {root && hits.length === 0 && !busy && q && <div className="muted pad">No matches.</div>}
        <div className="muted small" style={{ padding: "4px 10px" }}>
          {hits.length ? `${hits.length} matches${truncated ? " (truncated)" : ""}` : ""}
        </div>
        {Object.entries(byFile).map(([path, group]) => (
          <div key={path}>
            <div className="search-file">{path}</div>
            {group.map((h, i) => (
              <div key={i} className="search-hit" onClick={() => onOpen(path, h.line)}>
                <span className="ln">{h.line}</span>
                <span className="tx">{h.text}</span>
              </div>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
