/** Monaco <-> Vajra Core LSP bridge (diagnostics, completion, hover, definition). */
import { monaco } from "./monaco";
import type { Api } from "./api";

export interface LspCtx {
  api: Api;
  root: string;
}

type CtxGetter = () => LspCtx | null;
type PathOpener = (path: string, line: number) => void;

const LSP_LANGS: Record<string, string> = {
  python: "python",
  typescript: "typescript",
  javascript: "javascript",
  typescriptreact: "typescript",
  javascriptreact: "javascript",
};

let installed = false;
const debounce = new Map<string, ReturnType<typeof setTimeout>>();

function sev(n: number): monaco.MarkerSeverity {
  return (
    { 1: monaco.MarkerSeverity.Error, 2: monaco.MarkerSeverity.Warning, 3: monaco.MarkerSeverity.Info, 4: monaco.MarkerSeverity.Hint }[
      n
    ] ?? monaco.MarkerSeverity.Info
  );
}

export function refreshDiagnostics(getCtx: CtxGetter, model: monaco.editor.ITextModel, path: string, language: string) {
  const lang = LSP_LANGS[language];
  if (!lang) return;
  const key = model.uri.toString();
  clearTimeout(debounce.get(key));
  debounce.set(
    key,
    setTimeout(async () => {
      const ctx = getCtx();
      if (!ctx || model.isDisposed()) return;
      try {
        const r = await ctx.api.lspDiagnostics({ root: ctx.root, path, content: model.getValue(), language: lang });
        if (model.isDisposed()) return;
        const markers = (r.diagnostics || []).map((d: any) => ({
          startLineNumber: d.range.start.line + 1,
          startColumn: d.range.start.character + 1,
          endLineNumber: d.range.end.line + 1,
          endColumn: d.range.end.character + 1,
          message: d.message + (d.source ? ` (${d.source})` : ""),
          severity: sev(d.severity ?? 2),
        }));
        monaco.editor.setModelMarkers(model, "vajra-lsp", markers);
      } catch {
        /* offline / unsupported */
      }
    }, 500),
  );
}

export function installLsp(getCtx: CtxGetter, openPath: PathOpener) {
  if (installed) return;
  installed = true;

  for (const lang of ["python", "typescript", "javascript"]) {
    monaco.languages.registerCompletionItemProvider(lang, {
      triggerCharacters: [".", "(", "'", '"', "/"],
      async provideCompletionItems(model, position) {
        const ctx = getCtx();
        if (!ctx) return { suggestions: [] };
        const path = (model as any).__vajraPath as string | undefined;
        if (!path) return { suggestions: [] };
        try {
          const r = await ctx.api.lspCompletion({
            root: ctx.root,
            path,
            content: model.getValue(),
            language: lang,
            line: position.lineNumber - 1,
            character: position.column - 1,
          });
          const word = model.getWordUntilPosition(position);
          const range = new monaco.Range(position.lineNumber, word.startColumn, position.lineNumber, word.endColumn);
          return {
            suggestions: (r.items || []).map((it: any) => ({
              label: it.label,
              kind: (it.kind ?? 1) as monaco.languages.CompletionItemKind,
              insertText: it.insertText ?? it.textEdit?.newText ?? it.label,
              detail: it.detail,
              documentation:
                typeof it.documentation === "string" ? it.documentation : it.documentation?.value,
              sortText: it.sortText,
              range,
            })),
          };
        } catch {
          return { suggestions: [] };
        }
      },
    });

    monaco.languages.registerHoverProvider(lang, {
      async provideHover(model, position) {
        const ctx = getCtx();
        const path = (model as any).__vajraPath as string | undefined;
        if (!ctx || !path) return null;
        try {
          const r = await ctx.api.lspHover({
            root: ctx.root,
            path,
            content: model.getValue(),
            language: lang,
            line: position.lineNumber - 1,
            character: position.column - 1,
          });
          return r.value ? { contents: [{ value: r.value }] } : null;
        } catch {
          return null;
        }
      },
    });

    monaco.languages.registerDefinitionProvider(lang, {
      async provideDefinition(model, position) {
        const ctx = getCtx();
        const path = (model as any).__vajraPath as string | undefined;
        if (!ctx || !path) return null;
        try {
          const r = await ctx.api.lspDefinition({
            root: ctx.root,
            path,
            content: model.getValue(),
            language: lang,
            line: position.lineNumber - 1,
            character: position.column - 1,
          });
          const loc = (r.locations || [])[0];
          if (!loc) return null;
          const rel = loc.path.replace(ctx.root, "").replace(/^[\\/]+/, "").replace(/\\/g, "/");
          const sameFile = rel === path || loc.path.endsWith(path);
          if (!sameFile) {
            openPath(rel, loc.range.start.line + 1);
            return null;
          }
          return {
            uri: model.uri,
            range: new monaco.Range(
              loc.range.start.line + 1,
              loc.range.start.character + 1,
              loc.range.end.line + 1,
              loc.range.end.character + 1,
            ),
          };
        } catch {
          return null;
        }
      },
    });
  }
}
