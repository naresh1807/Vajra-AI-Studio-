import { useEffect, useRef } from "react";
import { monaco, langFor } from "./monaco";
import { installLsp, installInlineCompletions, installFormatters, LspCtx } from "./lsp";
import { acquireModel, releaseModel, syncModelContent, configureModels } from "./models";

export interface OpenDoc {
  path: string;
  content: string;
  dirty: boolean;
}

export type AssistAction =
  | "explain" | "fix" | "refactor" | "optimize" | "tests" | "document" | "security" | "edit";

const MENU: Array<{ id: AssistAction; label: string }> = [
  { id: "explain", label: "Vajra: Explain" },
  { id: "fix", label: "Vajra: Fix" },
  { id: "refactor", label: "Vajra: Refactor" },
  { id: "optimize", label: "Vajra: Optimize" },
  { id: "tests", label: "Vajra: Write Tests" },
  { id: "document", label: "Vajra: Document" },
  { id: "security", label: "Vajra: Security Review" },
];

export function EditorArea({
  docs,
  active,
  onActivate,
  onClose,
  onChange,
  onSave,
  onAssist,
  lspCtx,
  onOpenPath,
  reveal,
  inlineEnabled = true,
  breakpoints = [],
  onToggleBreakpoint,
  stoppedLine = null,
  actionRef,
  single = null,
  onSplit,
  onCloseSplit,
  onFocus,
}: {
  docs: OpenDoc[];
  active: string | null;
  onActivate: (path: string) => void;
  onClose: (path: string) => void;
  onChange: (path: string, content: string) => void;
  onSave: () => void;
  onAssist: (action: AssistAction, selection: string | null, instruction?: string) => void;
  lspCtx: () => LspCtx | null;
  onOpenPath: (path: string, line: number) => void;
  reveal: { path: string; line: number; n: number } | null;
  inlineEnabled?: boolean;
  breakpoints?: number[];
  onToggleBreakpoint?: (line: number) => void;
  stoppedLine?: number | null;
  actionRef?: { current: { format: () => void } | null };
  /** when set, this pane shows only this file (no tab bar) — the split view */
  single?: string | null;
  onSplit?: () => void;
  onCloseSplit?: () => void;
  onFocus?: () => void;
}) {
  const host = useRef<HTMLDivElement>(null);
  const editor = useRef<monaco.editor.IStandaloneCodeEditor | null>(null);
  const acquired = useRef<string | null>(null);
  const onChangeRef = useRef(onChange);
  const onSaveRef = useRef(onSave);
  const onAssistRef = useRef(onAssist);
  const lspCtxRef = useRef(lspCtx);
  const inlineEnabledRef = useRef(inlineEnabled);
  const onToggleBpRef = useRef(onToggleBreakpoint);
  const onFocusRef = useRef(onFocus);
  const decoRef = useRef<string[]>([]);
  onChangeRef.current = onChange;
  onSaveRef.current = onSave;
  onAssistRef.current = onAssist;
  lspCtxRef.current = lspCtx;
  inlineEnabledRef.current = inlineEnabled;
  onToggleBpRef.current = onToggleBreakpoint;
  onFocusRef.current = onFocus;

  const target = single ?? active;

  useEffect(() => {
    installLsp(() => lspCtxRef.current(), onOpenPath);
    installInlineCompletions(() => lspCtxRef.current(), () => inlineEnabledRef.current);
    installFormatters(() => lspCtxRef.current());
    configureModels((p, v) => onChangeRef.current(p, v), () => lspCtxRef.current());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!host.current) return;
    const ed = monaco.editor.create(host.current, {
      automaticLayout: true,
      theme: "vs-dark",
      fontSize: 13,
      minimap: { enabled: !single },
      scrollBeyondLastLine: false,
      tabSize: 2,
      inlineSuggest: { enabled: true },
      glyphMargin: true,
    });
    editor.current = ed;
    ed.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyS, () => onSaveRef.current());
    ed.onDidFocusEditorText(() => onFocusRef.current?.());
    ed.onMouseDown((e) => {
      if (e.target.type === monaco.editor.MouseTargetType.GUTTER_GLYPH_MARGIN && e.target.position) {
        onToggleBpRef.current?.(e.target.position.lineNumber);
      }
    });
    if (actionRef) {
      actionRef.current = {
        format: () => ed.getAction("editor.action.formatDocument")?.run(),
      };
    }

    const selText = () => {
      const sel = ed.getSelection();
      return sel && !sel.isEmpty() ? ed.getModel()?.getValueInRange(sel) ?? null : null;
    };

    for (const item of MENU) {
      ed.addAction({
        id: `vajra.${item.id}`,
        label: item.label,
        contextMenuGroupId: "vajra",
        contextMenuOrder: 1,
        run: () => onAssistRef.current(item.id, selText()),
      });
    }
    ed.addAction({
      id: "vajra.edit",
      label: "Vajra: Edit with instruction… (Ctrl+K)",
      keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyK],
      contextMenuGroupId: "vajra",
      contextMenuOrder: 0,
      run: () => {
        const instruction = window.prompt("Tell Vajra what to change:");
        if (instruction) onAssistRef.current("edit", selText(), instruction);
      },
    });

    return () => {
      ed.dispose();
      if (acquired.current) {
        releaseModel(acquired.current);
        acquired.current = null;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // attach the shared model for the target doc
  useEffect(() => {
    const ed = editor.current;
    if (!ed) return;
    if (!target) {
      ed.setModel(null);
      if (acquired.current) {
        releaseModel(acquired.current);
        acquired.current = null;
      }
      return;
    }
    const doc = docs.find((d) => d.path === target);
    if (!doc) return;

    if (acquired.current !== target) {
      const prev = acquired.current;
      const model = acquireModel(target, doc.content);
      acquired.current = target;
      if (prev) releaseModel(prev);
      ed.setModel(model);
    } else if (!doc.dirty) {
      syncModelContent(target, doc.content);
    }
    if (!single) ed.focus();
  }, [target, docs, single]);

  // breakpoint + stopped-line decorations (primary pane only)
  useEffect(() => {
    const ed = editor.current;
    if (!ed || single) return;
    const decos: monaco.editor.IModelDeltaDecoration[] = breakpoints.map((ln) => ({
      range: new monaco.Range(ln, 1, ln, 1),
      options: { isWholeLine: false, glyphMarginClassName: "bp-glyph" },
    }));
    if (stoppedLine) {
      decos.push({
        range: new monaco.Range(stoppedLine, 1, stoppedLine, 1),
        options: { isWholeLine: true, className: "stopped-line", glyphMarginClassName: "stopped-glyph" },
      });
    }
    decoRef.current = ed.deltaDecorations(decoRef.current, decos);
  }, [breakpoints, stoppedLine, target, single]);

  // reveal a line (from search / go-to-definition)
  useEffect(() => {
    if (!reveal || !editor.current || target !== reveal.path) return;
    const ed = editor.current;
    const t = setTimeout(() => {
      ed.revealLineInCenter(reveal.line);
      ed.setPosition({ lineNumber: reveal.line, column: 1 });
      ed.focus();
    }, 60);
    return () => clearTimeout(t);
  }, [reveal, target]);

  if (single) {
    const doc = docs.find((d) => d.path === single);
    return (
      <div className="editor-area split">
        <div className="tabs">
          <div className="tab active" title={single}>
            <span>{single.split("/").pop()}</span>
            {doc?.dirty && <span className="dot" />}
            <button className="x" onClick={() => onCloseSplit?.()} title="Close split">
              ×
            </button>
          </div>
        </div>
        <div className="monaco-host" ref={host} />
      </div>
    );
  }

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
        {docs.length > 0 && onSplit && (
          <button className="tab-split" onClick={onSplit} title="Split editor right (Ctrl+\)">
            ⇔
          </button>
        )}
      </div>
      <div className="monaco-host" ref={host} />
    </div>
  );
}
