import { useEffect, useRef } from "react";
import { monaco, langFor } from "./monaco";

export interface OpenDoc {
  path: string;
  content: string;
  dirty: boolean;
}

export function EditorArea({
  docs,
  active,
  onActivate,
  onClose,
  onChange,
  onSave,
}: {
  docs: OpenDoc[];
  active: string | null;
  onActivate: (path: string) => void;
  onClose: (path: string) => void;
  onChange: (path: string, content: string) => void;
  onSave: () => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  const editor = useRef<monaco.editor.IStandaloneCodeEditor | null>(null);
  const models = useRef<Map<string, monaco.editor.ITextModel>>(new Map());
  const onChangeRef = useRef(onChange);
  const onSaveRef = useRef(onSave);
  onChangeRef.current = onChange;
  onSaveRef.current = onSave;

  useEffect(() => {
    if (!host.current) return;
    editor.current = monaco.editor.create(host.current, {
      automaticLayout: true,
      theme: "vs-dark",
      fontSize: 13,
      minimap: { enabled: true },
      scrollBeyondLastLine: false,
      tabSize: 2,
    });
    editor.current.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => onSaveRef.current());
    return () => {
      editor.current?.dispose();
      models.current.forEach((m) => m.dispose());
      models.current.clear();
    };
  }, []);

  // sync model for the active doc
  useEffect(() => {
    if (!editor.current) return;
    if (!active) {
      editor.current.setModel(null);
      return;
    }
    const doc = docs.find((d) => d.path === active);
    if (!doc) return;
    let model = models.current.get(active);
    if (!model) {
      model = monaco.editor.createModel(doc.content, langFor(active));
      models.current.set(active, model);
      model.onDidChangeContent(() => onChangeRef.current(active, model!.getValue()));
    } else if (model.getValue() !== doc.content && !doc.dirty) {
      model.setValue(doc.content);
    }
    editor.current.setModel(model);
    editor.current.focus();
  }, [active, docs]);

  // drop models for closed docs
  useEffect(() => {
    const openPaths = new Set(docs.map((d) => d.path));
    for (const [path, model] of models.current) {
      if (!openPaths.has(path)) {
        model.dispose();
        models.current.delete(path);
      }
    }
  }, [docs]);

  return (
    <div className="editor-area">
      <div className="tabs">
        {docs.length === 0 && <div className="tab placeholder">No file open</div>}
        {docs.map((d) => (
          <div
            key={d.path}
            className={`tab ${d.path === active ? "active" : ""}`}
            onClick={() => onActivate(d.path)}
            title={d.path}
          >
            <span>{d.path.split("/").pop()}</span>
            {d.dirty && <span className="dot" />}
            <button
              className="x"
              onClick={(e) => {
                e.stopPropagation();
                onClose(d.path);
              }}
            >
              ×
            </button>
          </div>
        ))}
      </div>
      <div className="monaco-host" ref={host} />
    </div>
  );
}
