import { useEffect, useState } from "react";
import { monaco, langFor } from "./monaco";

export function StatusBar({
  core,
  root,
  activePath,
  problems,
  onProblemsClick,
}: {
  core: { ok: boolean; text: string };
  root: string | null;
  activePath: string | null;
  problems: { errors: number; warnings: number };
  onProblemsClick: () => void;
}) {
  const [pos, setPos] = useState<{ line: number; col: number } | null>(null);
  const [branch, setBranch] = useState("");

  useEffect(() => {
    const editors = monaco.editor.getEditors();
    const ed = editors[0];
    if (!ed) return;
    const update = () => {
      const p = ed.getPosition();
      if (p) setPos({ line: p.lineNumber, col: p.column });
    };
    update();
    const sub = ed.onDidChangeCursorPosition(update);
    return () => sub.dispose();
  }, [activePath]);

  useEffect(() => {
    // branch comes in via a custom event the GitPanel could dispatch; cheap poll fallback
    setBranch(root ? (window as any).__vajraBranch ?? "" : "");
  }, [root, activePath]);

  return (
    <footer className="statusbar">
      <span className={`sb-item ${core.ok ? "" : "bad"}`} title={core.text}>
        <span className={`dot ${core.ok ? "ok" : "bad"}`} /> {core.ok ? "Core" : "Core offline"}
      </span>
      {core.ok && core.text.includes(":") && (
        <span className="sb-item muted">{core.text.split("·").pop()?.trim()}</span>
      )}
      {branch && <span className="sb-item">⎇ {branch}</span>}
      <span className="sb-spacer" />
      <span className="sb-item sb-click" onClick={onProblemsClick} title="Problems">
        ✕ {problems.errors} &nbsp; ▲ {problems.warnings}
      </span>
      {activePath && <span className="sb-item muted">{langFor(activePath)}</span>}
      {pos && <span className="sb-item muted">Ln {pos.line}, Col {pos.col}</span>}
    </footer>
  );
}
