import { useEffect, useRef } from "react";
import { monaco, langFor } from "./monaco";

export function DiffModal({
  path,
  original,
  proposed,
  title,
  onAccept,
  onReject,
}: {
  path: string;
  original: string;
  proposed: string;
  title: string;
  onAccept: () => void;
  onReject: () => void;
}) {
  const host = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!host.current) return;
    const lang = langFor(path);
    const editor = monaco.editor.createDiffEditor(host.current, {
      automaticLayout: true,
      theme: "vs-dark",
      readOnly: true,
      renderSideBySide: true,
      fontSize: 12,
      minimap: { enabled: false },
    });
    editor.setModel({
      original: monaco.editor.createModel(original, lang),
      modified: monaco.editor.createModel(proposed, lang),
    });
    return () => {
      const m = editor.getModel();
      m?.original.dispose();
      m?.modified.dispose();
      editor.dispose();
    };
  }, [path, original, proposed]);

  return (
    <div className="modal-bg">
      <div className="modal diff-modal">
        <div className="diff-head">
          <b>{title}</b>
          <span className="muted small">{path}</span>
          <div className="spacer" />
          <button onClick={onReject}>Reject</button>
          <button className="primary" onClick={onAccept}>
            Accept &amp; Save
          </button>
        </div>
        <div className="diff-host" ref={host} />
      </div>
    </div>
  );
}
