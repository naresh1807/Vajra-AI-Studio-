import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Api, DebugState, FileNode, loadSettings, saveSettings, Settings } from "./api";
import { AssistAction, EditorArea, OpenDoc } from "./Editor";
import { FileTree } from "./FileTree";
import { BottomPanel } from "./BottomPanel";
import { AgentPanel } from "./AgentPanel";
import { DiffModal } from "./DiffModal";
import { FolderPicker } from "./FolderPicker";
import { GitPanel } from "./GitPanel";
import { SearchPanel } from "./SearchPanel";
import { CommandPalette, Command } from "./CommandPalette";
import { StatusBar } from "./StatusBar";
import { langFor, monaco } from "./monaco";

export interface Problem {
  path: string;
  line: number;
  severity: number;
  message: string;
}

function flattenFiles(node: FileNode | null, out: string[] = []): string[] {
  for (const c of node?.children ?? []) {
    if (c.type === "file") out.push(c.path);
    else flattenFiles(c, out);
  }
  return out;
}

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
  const [leftTab, setLeftTab] = useState<"explorer" | "git" | "search">("explorer");
  const [palette, setPalette] = useState<"commands" | "files" | null>(null);
  const [reveal, setReveal] = useState<{ path: string; line: number; n: number } | null>(null);
  const [bps, setBps] = useState<Record<string, number[]>>({});
  const [problems, setProblems] = useState<Problem[]>([]);
  const [debug, setDebug] = useState<DebugState | null>(null);
  const [debugFrame, setDebugFrame] = useState<{ path: string; line: number } | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const editorApiRef = useRef<{ format: () => void } | null>(null);

  const sep = root && root.includes("\\") ? "\\" : "/";
  const abs = (rel: string) => `${root}${sep}${rel.replace(/\//g, sep)}`;
  const toRel = (p: string) =>
    root ? p.replace(root, "").replace(/^[\\/]+/, "").replace(/\\/g, "/") : p;

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

  const openFileAt = useCallback(
    (path: string, line: number) => {
      void openFile(path);
      setReveal({ path, line, n: Date.now() });
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [docs, root],
  );

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

  const commands: Command[] = useMemo(
    () => [
      { id: "openFolder", label: "Open Folder…", run: openFolder },
      { id: "save", label: "Save File", hint: "Ctrl+S", run: () => void saveActive() },
      {
        id: "format",
        label: "Format Document",
        hint: "Shift+Alt+F",
        run: () => editorApiRef.current?.format(),
      },
      { id: "explorer", label: "View: Explorer", run: () => setLeftTab("explorer") },
      { id: "search", label: "View: Search", hint: "Ctrl+Shift+F", run: () => setLeftTab("search") },
      { id: "scm", label: "View: Source Control", run: () => setLeftTab("git") },
      { id: "checkpoint", label: "Git: Create Checkpoint", run: () => root && api.gitCheckpoint(root, "manual").then(() => setToast("checkpoint created")) },
      { id: "assist.fix", label: "Vajra: Fix (active file)", run: () => runAssist("fix", null) },
      { id: "assist.refactor", label: "Vajra: Refactor (active file)", run: () => runAssist("refactor", null) },
      { id: "assist.tests", label: "Vajra: Write Tests (active file)", run: () => runAssist("tests", null) },
      { id: "assist.explain", label: "Vajra: Explain (active file)", run: () => runAssist("explain", null) },
      { id: "assist.security", label: "Vajra: Security Review (active file)", run: () => runAssist("security", null) },
      { id: "settings", label: "Open Settings", run: () => setShowSettings(true) },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [root, api, saveActive, runAssist],
  );

  const fileList = useMemo(() => flattenFiles(tree), [tree]);

  useEffect(() => {
    const collect = () => {
      const markers = monaco.editor.getModelMarkers({ owner: "vajra-lsp" });
      setProblems(
        markers
          .map((m) => {
            const model = monaco.editor.getModels().find((x) => x.uri.toString() === m.resource.toString());
            const path = (model as any)?.__vajraPath as string | undefined;
            return path ? { path, line: m.startLineNumber, severity: m.severity, message: m.message } : null;
          })
          .filter(Boolean) as Problem[],
      );
    };
    collect();
    const sub = monaco.editor.onDidChangeMarkers(collect);
    return () => sub.dispose();
  }, []);

  const problemCounts = useMemo(
    () => ({
      errors: problems.filter((p) => p.severity === 8).length,
      warnings: problems.filter((p) => p.severity === 4).length,
    }),
    [problems],
  );

  function toggleBp(line: number) {
    if (!active) return;
    setBps((b) => {
      const cur = new Set(b[active] ?? []);
      cur.has(line) ? cur.delete(line) : cur.add(line);
      const lines = [...cur].sort((x, y) => x - y);
      const next = { ...b, [active]: lines };
      if (debug && debug.state !== "terminated") void api.debugBreakpoints(debug.id, abs(active), lines);
      return next;
    });
  }

  async function startDebug() {
    if (!root || !active) {
      setToast("Open a Python file to debug.");
      return;
    }
    if (!active.endsWith(".py")) {
      setToast("Debugging currently supports Python files.");
      return;
    }
    try {
      const absBps: Record<string, number[]> = {};
      for (const [rel, lines] of Object.entries(bps)) if (lines.length) absBps[abs(rel)] = lines;
      const s = await api.debugStart(root, active, absBps);
      setDebug(s);
    } catch (e) {
      setToast(`debug: ${e}`);
    }
  }

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "F5" && !debug) {
        e.preventDefault();
        void startDebug();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [root, active, bps, debug]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.ctrlKey && e.shiftKey && (e.key === "P" || e.key === "p")) {
        e.preventDefault();
        setPalette("commands");
      } else if (e.ctrlKey && !e.shiftKey && (e.key === "P" || e.key === "p")) {
        e.preventDefault();
        setPalette("files");
      } else if (e.ctrlKey && e.shiftKey && (e.key === "F" || e.key === "f")) {
        e.preventDefault();
        setLeftTab("search");
      } else if (e.key === "Escape") {
        setPalette(null);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className="studio">
      <header className="topbar">
        <div className="brand">⚡ VAJRA&nbsp;AI&nbsp;STUDIO</div>
        <button className="tb" onClick={openFolder}>
          {root ? root.split(/[\\/]/).pop() : "Open Folder"}
        </button>
        <button className="tb" onClick={startDebug} title="Debug active Python file (F5)" disabled={!!debug}>
          ▷ Debug
        </button>
        <div className="spacer" />
        <span className={`dot ${core.ok ? "ok" : "bad"}`} title={core.text} />
        <span className="muted small">{core.text}</span>
        <button className="tb" onClick={() => setShowSettings(true)}>
          Settings
        </button>
      </header>

      {!core.ok && !showSettings && (
        <div className="offline-banner">
          <b>Vajra Core is offline.</b> Start it:
          <code onClick={() => navigator.clipboard?.writeText("vajra-api")}>vajra-api</code>
          <span className="muted">(or&nbsp;</span>
          <code onClick={() => navigator.clipboard?.writeText("pwsh -File scripts/dev.ps1")}>
            pwsh -File scripts/dev.ps1
          </code>
          <span className="muted">). Click to copy · retrying…</span>
        </div>
      )}

      <div className="body">
        <div className="left">
          <div className="left-tabs">
            <button className={leftTab === "explorer" ? "on" : ""} onClick={() => setLeftTab("explorer")}>
              Explorer
            </button>
            <button className={leftTab === "search" ? "on" : ""} onClick={() => setLeftTab("search")}>
              Search
            </button>
            <button className={leftTab === "git" ? "on" : ""} onClick={() => setLeftTab("git")}>
              Source Control
            </button>
          </div>
          {leftTab === "explorer" && (
            <FileTree tree={tree} activePath={active} onOpen={openFile} onRefresh={() => root && loadTree(root)} />
          )}
          {leftTab === "git" && <GitPanel api={api} root={root} onChanged={() => root && loadTree(root)} />}
          {leftTab === "search" && <SearchPanel api={api} root={root} onOpen={openFileAt} />}
        </div>
        <div className="center">
          <EditorArea
            docs={docs}
            active={active}
            onActivate={setActive}
            onClose={closeDoc}
            onChange={changeDoc}
            onSave={saveActive}
            onAssist={runAssist}
            lspCtx={() => (root ? { api, root } : null)}
            onOpenPath={openFileAt}
            reveal={reveal}
            inlineEnabled={settings.inlineCompletions}
            breakpoints={active ? bps[active] ?? [] : []}
            onToggleBreakpoint={toggleBp}
            stoppedLine={debugFrame && active && debugFrame.path.endsWith(active) ? debugFrame.line : null}
            actionRef={editorApiRef}
          />
          <BottomPanel
            api={api}
            root={root}
            events={events}
            debug={debug}
            setDebug={setDebug}
            onDebugFrame={(p, line) => {
              const rel = toRel(p);
              void openFile(rel);
              setDebugFrame({ path: p, line });
              setReveal({ path: rel, line, n: Date.now() });
            }}
            onOpenAt={openFileAt}
            problems={problems}
          />
        </div>
        <AgentPanel api={api} root={root} onFilesChanged={() => root && loadTree(root)} />
      </div>

      <StatusBar
        core={core}
        root={root}
        activePath={active}
        problems={problemCounts}
        onProblemsClick={() =>
          window.dispatchEvent(new CustomEvent("vajra:bottom-tab", { detail: "problems" }))
        }
      />

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

      {palette && (
        <CommandPalette
          mode={palette}
          commands={commands}
          files={fileList}
          onClose={() => setPalette(null)}
          onPickFile={(p) => openFile(p)}
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
        <label style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 12 }}>
          <input
            type="checkbox"
            style={{ width: "auto" }}
            checked={d.inlineCompletions}
            onChange={(e) => setD({ ...d, inlineCompletions: e.target.checked })}
          />
          AI inline completions — ghost text, Tab to accept
        </label>
        <div className="muted small" style={{ marginTop: 4 }}>
          Best with a fast local coding model (Ollama qwen2.5-coder). Hosted reasoning
          models are slow for this and suggestions may be sparse.
        </div>
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
