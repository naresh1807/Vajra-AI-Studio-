/** Monaco setup — bundled workers (no CDN, local-first). */
import * as monaco from "monaco-editor";
import editorWorker from "monaco-editor/esm/vs/editor/editor.worker?worker";
import jsonWorker from "monaco-editor/esm/vs/language/json/json.worker?worker";
import cssWorker from "monaco-editor/esm/vs/language/css/css.worker?worker";
import htmlWorker from "monaco-editor/esm/vs/language/html/html.worker?worker";
import tsWorker from "monaco-editor/esm/vs/language/typescript/ts.worker?worker";

self.MonacoEnvironment = {
  getWorker(_: string, label: string) {
    if (label === "json") return new jsonWorker();
    if (label === "css" || label === "scss" || label === "less") return new cssWorker();
    if (label === "html" || label === "handlebars" || label === "razor") return new htmlWorker();
    if (label === "typescript" || label === "javascript") return new tsWorker();
    return new editorWorker();
  },
};

const EXT_LANG: Record<string, string> = {
  ts: "typescript", tsx: "typescript", mts: "typescript", cts: "typescript",
  js: "javascript", jsx: "javascript", mjs: "javascript", cjs: "javascript",
  py: "python", pyi: "python", rs: "rust", go: "go", java: "java", kt: "kotlin",
  c: "c", h: "c", cpp: "cpp", hpp: "cpp", cc: "cpp", cxx: "cpp", hh: "cpp",
  cs: "csharp", php: "php", rb: "ruby", swift: "swift", lua: "lua", r: "r",
  dart: "dart", scala: "scala", clj: "clojure", ex: "elixir", exs: "elixir",
  json: "json", jsonc: "json", yaml: "yaml", yml: "yaml", toml: "ini",
  md: "markdown", markdown: "markdown", html: "html", htm: "html", vue: "html",
  css: "css", scss: "scss", less: "less",
  sh: "shell", bash: "shell", zsh: "shell", ps1: "powershell",
  bat: "bat", cmd: "bat", sql: "sql", xml: "xml", svg: "xml",
  graphql: "graphql", gql: "graphql", proto: "proto",
  ini: "ini", cfg: "ini", conf: "ini", dockerfile: "dockerfile",
};

const NAME_LANG: Record<string, string> = {
  dockerfile: "dockerfile", makefile: "makefile", ".gitignore": "plaintext",
  ".env": "shell", ".bashrc": "shell", ".zshrc": "shell",
};

export function langFor(path: string): string {
  const base = (path.split("/").pop() ?? "").toLowerCase();
  if (NAME_LANG[base]) return NAME_LANG[base];
  const ext = base.includes(".") ? base.split(".").pop()! : "";
  return EXT_LANG[ext] ?? "plaintext";
}

export { monaco };
