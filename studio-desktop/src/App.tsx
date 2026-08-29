import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Api, FileNode, loadSettings, saveSettings, Settings } from "./api";
import { AssistAction, EditorArea, OpenDoc } from "./Editor";
import { FileTree } from "./FileTree";
import { BottomPanel } from "./BottomPanel";
import { AgentPanel } from "./AgentPanel";
import { DiffModal } from "./DiffModal";
import { FolderPicker } from "./FolderPicker";
import { langFor } from "./monaco";

async function tauriPickFolder(): Promise<string | null> {
  const t = (window as any).__TAURI__;
  if (!t?.dialog?.open) return null;
  const picked = await t.dialog.open({ directory: true, multiple: false });
  return typeof picked === "string" ? picked : null;
}

interface PendingDiff {
  path: string;
  original: string;
  proposed: string;
  title: string;
}

export function App() {
  const [settings, setSettings] = useState<Settings>(loadSettings());
  const api = useMemo(() => new Api(settings), [settings]);

  const [core, setCore] = useState<{ ok: boolean; text: string }>({ ok: false, text: "connecting…" });
  const [root, setRoot] = useState<string | null>(settings.lastWorkspace || null);
  const [tree, setTree] = useState<FileNode | null>(null);
  const [docs, setDocs] = useState<OpenDoc[]>([]);
  const [active, setActive] = useState<string | null>(null);
  const [events, setEvents] = useState<any[]>([]);
  const [showSettings, setShowSettings] = useState(!settings.pairingToken || settings.pairingToken === "change-me-local-only");
  const [toast, setToast] = useState("");
  const [pendingDiff, setPendingDiff] = useState<PendingDiff | null>(null);
  const [assisting, setAssisting] = useState(false);
  const [prose, setProse] = useState<{ title: string; text: string } | null>(null);
  const [showPicker, setShowPicker] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  const refreshHealth = useCallback(async () => {
    try {
      const h = await api.health();
      setCore({ ok: true, text: `Core ${h.version} · ${Object.values(h.models)[0]}` });
    } catch (e) {
      setCore({ ok: false, text: "Core offline" });
    }
  }, [api]);

  useEffect(() => {
    void refreshHealth();
    const t = setInterval(refreshHealth, 5000);
    return () => clearInterval(t);
  }, [refreshHealth]);

  useEffect(() => {
    try {
      const ws = api.events((e) => setEvents((p) => [...p.slice(-400), e]));
      wsRef.current = ws;
      return () => ws.close();
    } catch {
      return;
    }
  }, [api]);

  const loadTree = useCallback(
    async (r: string) => {
      try {
        setTree(await api.tree(r));
      } catch (e) {
        setToast(`tree: ${e}`);
      }
    },
    [api],
  );

  useEffect(() => {
    if (root) void loadTree(root);
  }, [root, loadTree]);

  const commitRoot = useCallback(
    (path: string) => {
      setRoot(path);
      setDocs([]);
      setActive(null);
      const next = { ...settings, lastWorkspace: path };
      setSettings(next);
      saveSettings(next);
    },
    [settings],
  );

  const pickAndOpen = useCallback(
    async (path: string) => {
      setShowPicker(false);
      try {
        commitRoot((await api.openProject(path, true)).root_path);
      } catch (e) {
        setToast(`open: ${e}`);
      }
    },
    [api, commitRoot],
  );

  async function openFolder() {
    const native = await tauriPickFolder();
    if (native) {
      void pickAndOpen(native);
      return;
    }
    setShowPicker(true);
  }

  async function openFile(path: string) {
    setActive(path);
    if (docs.some((d) => d.path === path)) return;
    setDocs((d) => [...d, { path, content: "", dirty: false }]);
    try {
      const f = await api.readFile(root!, path);
      setDocs((d) => d.map((x) => (x.path === path ? { ...x, content: f.content } : x)));
    } catch (e) {
      setToast(`read: ${e}`);
      setDocs((d) => d.filter((x) => x.path !== path));
    }
  }

  function changeDoc(path: string, content: string) {
    setDocs((d) => d.map((x) => (x.path === path ? { ...x, content, dirty: true } : x)));
  }

  const saveActive = useCallback(async () => {
    const doc = docs.find((d) => d.path === active);
    if (!doc || !doc.dirty || !root) return;
    try {
      const r = await api.writeFile(root, doc.path, doc.content);
      setDocs((d) => d.map((x) => (x.path === doc.path ? { ...x, dirty: false } : x)));
      setToast(`saved ${doc.path}${r.created ? " (new)" : ""}`);
      void loadTree(root);
    } catch (e) {
      setToast(`save: ${e}`);
    }
  }, [docs, active, root, api, loadTree]);

  const runAssist = useCallback(
    async (action: AssistAction, selection: string | null, instruction?: string) => {
      const doc = docs.find((d) => d.path === active);
      if (!doc || !root || assisting) return;
      setAssisting(true);
      setToast(`Vajra: ${action}…`);
      try {
        const r = await api.assist({
          root,
          path: doc.path,
          action,
          selection,
          instruction,
          language: langFor(doc.path),
        });
        if (r.kind === "prose") {
          setProse({ title: `Vajra — ${action}`, text: r.text });
        } else if (r.new_content && r.new_content !== doc.content) {
          setPendingDiff({
            path: doc.path,
            original: doc.content,
            proposed: r.new_content,
            title: `Vajra — ${action}`,
          });
        } else {
          setToast("No change proposed.");
        }
      } catch (e) {
        setToast(`assist: ${e}`);
      } finally {
        setAssisting(false);
      }
    },
    [docs, active, root, api, assisting],
  );

  async function acceptDiff() {
    if (!pendingDiff || !root) return;
    const { path, proposed } = pendingDiff;
    setPendingDiff(null);
    try {
      await api.writeFile(root, path, proposed);
      setDocs((d) => d.map((x) => (x.path === path ? { ...x, content: proposed, dirty: false } : x)));
      setToast(`applied to ${path}`);
      void loadTree(root);
    } catch (e) {
      setToast(`apply: ${e}`);
    }
  }

  function closeDoc(path: string) {
    setDocs((d) => d.filter((x) => x.path !== path));
    if (active === path) {
      const rest = docs.filter((x) => x.path !== path);
      setActive(rest.length ? rest[rest.length - 1].path : null);
    }
  }

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(""), 3000);
    return () => clearTimeout(t);
  }, [toast]);

  return (
    <div className="studio">
      <header className="topbar">
        <div className="brand">⚡ VAJRA&nbsp;AI&nbsp;STUDIO</div>
        <button className="tb" onClick={openFolder}>
          {root ? root.split(/[\\/]/).pop() : "Open Folder"}
        </button>
        <div className="spacer" />
        <span className={`dot ${core.ok ? "ok" : "bad"}`} title={core.text} />
        <span className="muted small">{core.text}</span>
        <button className="tb" onClick={() => setShowSettings(true)}>
          Settings
        </button>
      </header>

      <div className="body">
        <FileTree tree={tree} activePath={active} onOpen={openFile} onRefresh={() => root && loadTree(root)} />
        <div className="center">
          <EditorArea
            docs={docs}
            active={active}
            onActivate={setActive}
            onClose={closeDoc}
            onChange={changeDoc}
            onSave={saveActive}
            onAssist={runAssist}
          />
          <BottomPanel api={api} root={root} events={events} />
        </div>
        <AgentPanel api={api} root={root} onFilesChanged={() => root && loadTree(root)} />
      </div>

      {toast && <div className="toast">{toast}</div>}

      {pendingDiff && (
        <DiffModal
          path={pendingDiff.path}
          original={pendingDiff.original}
          proposed={pendingDiff.proposed}
          title={pendingDiff.title}
          onAccept={acceptDiff}
          onReject={() => setPendingDiff(null)}
        />
      )}

      {showPicker && (
        <FolderPicker
          api={api}
          start={settings.lastWorkspace || root || ""}
          onPick={pickAndOpen}
          onClose={() => setShowPicker(false)}
        />
      )}

      {prose && (
        <div className="modal-bg" onClick={() => setProse(null)}>
          <div className="modal prose-modal" onClick={(e) => e.stopPropagation()}>
            <div className="row">
              <b>{prose.title}</b>
              <div className="spacer" />
              <button onClick={() => setProse(null)}>Close</button>
            </div>
            <pre className="prose-body">{prose.text}</pre>
          </div>
        </div>
      )}

      {showSettings && (
        <SettingsModal
          settings={settings}
          onClose={() => setShowSettings(false)}
          onSave={(s) => {
            setSettings(s);
            saveSettings(s);
            setShowSettings(false);
            void refreshHealth();
          }}
        />
      )}
    </div>
  );
}

function SettingsModal({
  settings,
  onSave,
  onClose,
}: {
  settings: Settings;
  onSave: (s: Settings) => void;
  onClose: () => void;
}) {
  const [d, setD] = useState(settings);
  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h2>Settings</h2>
        <label>Vajra Local API URL</label>
        <input value={d.apiUrl} onChange={(e) => setD({ ...d, apiUrl: e.target.value })} />
        <label>Pairing token (matches VAJRA_PAIRING_TOKEN in .env)</label>
        <input value={d.pairingToken} onChange={(e) => setD({ ...d, pairingToken: e.target.value })} />
        <div className="row end">
          <button onClick={onClose}>Cancel</button>
          <button className="primary" onClick={() => onSave(d)}>
            Save
          </button>
        </div>
      </div>
    </div>
  );
}
