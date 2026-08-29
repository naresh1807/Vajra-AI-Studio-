import { useCallback, useEffect, useState } from "react";
import type { Api } from "./api";

interface GStatus {
  is_repo: boolean;
  branch: string;
  ahead: number;
  behind: number;
  files: Array<{ path: string; staged: boolean; unstaged: boolean; status: string }>;
}

export function GitPanel({
  api,
  root,
  onChanged,
}: {
  api: Api;
  root: string | null;
  onChanged: () => void;
}) {
  const [st, setSt] = useState<GStatus | null>(null);
  const [msg, setMsg] = useState("");
  const [diff, setDiff] = useState<{ path: string; text: string } | null>(null);
  const [cps, setCps] = useState<Array<{ tag: string; date: string; subject: string }>>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const refresh = useCallback(async () => {
    if (!root) return;
    try {
      const s = await api.gitStatus(root);
      setSt(s);
      (window as any).__vajraBranch = s.is_repo ? s.branch : "";
      setCps(await api.gitCheckpoints(root));
    } catch (e) {
      setErr(String(e));
    }
  }, [api, root]);

  useEffect(() => {
    void refresh();
    const t = setInterval(refresh, 4000);
    return () => clearInterval(t);
  }, [refresh]);

  const act = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setErr("");
    try {
      await fn();
      await refresh();
      onChanged();
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  };

  async function showDiff(path: string, staged: boolean) {
    try {
      const d = await api.gitDiff(root!, path, staged);
      setDiff({ path, text: d.diff || "(no diff)" });
    } catch (e) {
      setErr(String(e));
    }
  }

  if (!root) return <div className="muted pad">Open a folder.</div>;
  if (st && !st.is_repo)
    return (
      <div className="pad">
        <div className="muted">Not a Git repository.</div>
        <button className="mini" style={{ marginTop: 8 }} onClick={() => act(() => api.gitCheckpoint(root, "init"))}>
          Initialise with a checkpoint
        </button>
      </div>
    );

  const staged = st?.files.filter((f) => f.staged) ?? [];
  const unstaged = st?.files.filter((f) => !f.staged) ?? [];

  return (
    <div className="gitpanel">
      <div className="git-branch">
        <b>{st?.branch || "…"}</b>
        {!!st?.ahead && <span className="muted small"> ↑{st.ahead}</span>}
        {!!st?.behind && <span className="muted small"> ↓{st.behind}</span>}
        <div className="spacer" />
        <button className="mini" disabled={busy} onClick={() => act(() => api.gitCheckpoint(root, "manual"))}>
          + Checkpoint
        </button>
      </div>

      <div className="git-commit">
        <input placeholder="commit message" value={msg} onChange={(e) => setMsg(e.target.value)} />
        <div className="row">
          <button
            className="mini"
            disabled={busy || !unstaged.length}
            onClick={() => act(() => api.gitStage(root, []))}
          >
            Stage all
          </button>
          <button
            className="mini on"
            disabled={busy || !msg.trim() || !staged.length}
            onClick={() => act(async () => { await api.gitCommit(root, msg); setMsg(""); })}
          >
            Commit ({staged.length})
          </button>
        </div>
      </div>

      {err && <div className="picker-err">{err}</div>}

      <div className="git-scroll">
        {staged.length > 0 && <div className="git-section">Staged</div>}
        {staged.map((f) => (
          <div key={f.path} className="git-row">
            <span className={`git-tag ${f.status}`}>{f.status[0].toUpperCase()}</span>
            <span className="git-path" onClick={() => showDiff(f.path, true)}>{f.path}</span>
            <div className="spacer" />
            <button className="git-x" title="Unstage" onClick={() => act(() => api.gitUnstage(root, [f.path]))}>
              −
            </button>
          </div>
        ))}

        {unstaged.length > 0 && <div className="git-section">Changes</div>}
        {unstaged.map((f) => (
          <div key={f.path} className="git-row">
            <span className={`git-tag ${f.status}`}>{f.status[0].toUpperCase()}</span>
            <span className="git-path" onClick={() => showDiff(f.path, false)}>{f.path}</span>
            <div className="spacer" />
            <button
              className="git-x"
              title="Discard changes"
              onClick={() => window.confirm(`Discard changes to ${f.path}?`) && act(() => api.gitDiscard(root, f.path))}
            >
              ⨯
            </button>
            <button className="git-x" title="Stage" onClick={() => act(() => api.gitStage(root, [f.path]))}>
              +
            </button>
          </div>
        ))}
        {st && st.files.length === 0 && <div className="muted pad">Working tree clean.</div>}

        {cps.length > 0 && <div className="git-section">Vajra checkpoints</div>}
        {cps.map((c) => (
          <div key={c.tag} className="git-row">
            <span className="git-path" title={c.subject}>{c.tag.replace("vajra/", "")}</span>
            <div className="spacer" />
            <button
              className="git-restore"
              title="Roll back to this checkpoint"
              onClick={() =>
                window.confirm(`Hard-reset the working tree to ${c.tag}?\nUncommitted changes will be lost.`) &&
                act(() => api.gitRestore(root, c.tag))
              }
            >
              ↺ restore
            </button>
          </div>
        ))}
      </div>

      {diff && (
        <div className="modal-bg" onClick={() => setDiff(null)}>
          <div className="modal prose-modal" onClick={(e) => e.stopPropagation()}>
            <div className="row">
              <b>{diff.path}</b>
              <div className="spacer" />
              <button onClick={() => setDiff(null)}>Close</button>
            </div>
            <pre className="prose-body diff-text">{diff.text}</pre>
          </div>
        </div>
      )}
    </div>
  );
}
