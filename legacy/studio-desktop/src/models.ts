/** Shared Monaco model registry so multiple editor panes (split view) edit the
 *  same underlying model — edits and diagnostics stay in sync. Ref-counted:
 *  a model is disposed when the last pane releases it. */
import { monaco, langFor } from "./monaco";
import { refreshDiagnostics, type LspCtx } from "./lsp";

type Entry = { model: monaco.editor.ITextModel; refs: number };
const reg = new Map<string, Entry>();

let onChange: (path: string, value: string) => void = () => {};
let getCtx: () => LspCtx | null = () => null;
let quiet = false;

export function configureModels(change: (p: string, v: string) => void, ctx: () => LspCtx | null) {
  onChange = change;
  getCtx = ctx;
}

export function acquireModel(path: string, content: string): monaco.editor.ITextModel {
  let e = reg.get(path);
  if (!e) {
    const language = langFor(path);
    const model = monaco.editor.createModel(content, language);
    (model as any).__vajraPath = path;
    model.onDidChangeContent(() => {
      if (quiet) return;
      onChange(path, model.getValue());
      refreshDiagnostics(() => getCtx(), model, path, language);
    });
    refreshDiagnostics(() => getCtx(), model, path, language);
    e = { model, refs: 0 };
    reg.set(path, e);
  }
  e.refs++;
  return e.model;
}

export function releaseModel(path: string) {
  const e = reg.get(path);
  if (!e) return;
  e.refs -= 1;
  if (e.refs <= 0) {
    e.model.dispose();
    reg.delete(path);
  }
}

/** Push externally-changed content (file load, accepted diff) without marking dirty. */
export function syncModelContent(path: string, content: string) {
  const e = reg.get(path);
  if (e && e.model.getValue() !== content) {
    quiet = true;
    e.model.setValue(content);
    quiet = false;
  }
}
