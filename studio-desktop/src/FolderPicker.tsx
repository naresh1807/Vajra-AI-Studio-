import { useCallback, useEffect, useState } from "react";
import type { Api } from "./api";

export function FolderPicker({
  api,
  start,
  onPick,
  onClose,
}: {
  api: Api;
  start: string;
  onPick: (path: string) => void;
  onClose: () => void;
}) {
  const [path, setPath] = useState(start);
  const [parent, setParent] = useState<string | null>(null);
  const [entries, setEntries] = useState<Array<{ name: string; path: string }>>([]);
  const [err, setErr] = useState("");
  const [newName, setNewName] = useState("");

  const load = useCallback(
    async (p: string) => {
      setErr("");
      try {
        const r = await api.fsList(p);
        setPath(r.path);
        setParent(r.parent);
        setEntries(r.entries);
      } catch (e) {
        setErr(String(e));
      }
    },
    [api],
  );

  useEffect(() => {
    void load(start);
  }, [load, start]);

  async function makeFolder() {
    const name = newName.trim();
    if (!name || !path) return;
    const sep = path.endsWith("\\") || path.endsWith("/") ? "" : path.includes("\\") ? "\\" : "/";
    const full = `${path}${sep}${name}`;
    try {
      const r = await api.fsMkdir(full);
      setNewName("");
      await load(r.path);
    } catch (e) {
      setErr(String(e));
    }
  }

  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="modal picker" onClick={(e) => e.stopPropagation()}>
        <div className="row">
          <b>Open Folder</b>
          <div className="spacer" />
          <button onClick={() => load("")}>Drives</button>
          <button disabled={!parent} onClick={() => parent && load(parent)}>
            ↑ Up
          </button>
        </div>

        <div className="picker-path">{path || "(drives)"}</div>

        <div className="picker-list">
          {entries.length === 0 && <div className="muted pad">No sub-folders.</div>}
          {entries.map((e) => (
            <div key={e.path} className="picker-row" onDoubleClick={() => load(e.path)} onClick={() => setPath(e.path)}>
              <span className="ico">▸</span>
              {e.name}
            </div>
          ))}
        </div>

        {err && <div className="picker-err">{err}</div>}

        <div className="row" style={{ marginTop: 10 }}>
          <input
            placeholder="new folder name"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && makeFolder()}
          />
          <button onClick={makeFolder} disabled={!newName.trim()}>
            + New
          </button>
        </div>

        <div className="row end">
          <button onClick={onClose}>Cancel</button>
          <button className="primary" disabled={!path} onClick={() => onPick(path)}>
            Open this folder
          </button>
        </div>
      </div>
    </div>
  );
}
