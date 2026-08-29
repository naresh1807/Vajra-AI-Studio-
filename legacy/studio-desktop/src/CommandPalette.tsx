import { useEffect, useMemo, useRef, useState } from "react";

export interface Command {
  id: string;
  label: string;
  hint?: string;
  run: () => void;
}

function fuzzy(needle: string, hay: string): number {
  needle = needle.toLowerCase();
  hay = hay.toLowerCase();
  if (!needle) return 1;
  let n = 0;
  let score = 0;
  let last = -1;
  for (let i = 0; i < hay.length && n < needle.length; i++) {
    if (hay[i] === needle[n]) {
      score += last === i - 1 ? 3 : 1;
      last = i;
      n++;
    }
  }
  return n === needle.length ? score : 0;
}

export function CommandPalette({
  mode,
  commands,
  files,
  onClose,
  onPickFile,
}: {
  mode: "commands" | "files";
  commands: Command[];
  files: string[];
  onClose: () => void;
  onPickFile: (path: string) => void;
}) {
  const [q, setQ] = useState("");
  const [sel, setSel] = useState(0);
  const listRef = useRef<HTMLDivElement>(null);

  const items = useMemo(() => {
    if (mode === "files") {
      return files
        .map((f) => ({ key: f, label: f, score: fuzzy(q, f) }))
        .filter((x) => x.score > 0 || !q)
        .sort((a, b) => b.score - a.score)
        .slice(0, 50);
    }
    return commands
      .map((c) => ({ key: c.id, label: c.label, hint: c.hint, score: fuzzy(q, c.label), run: c.run }))
      .filter((x) => x.score > 0 || !q)
      .sort((a, b) => b.score - a.score);
  }, [q, mode, files, commands]);

  useEffect(() => setSel(0), [q, mode]);
  useEffect(() => {
    listRef.current?.children[sel]?.scrollIntoView({ block: "nearest" });
  }, [sel]);

  function choose(i: number) {
    const it = items[i] as any;
    if (!it) return;
    onClose();
    if (mode === "files") onPickFile(it.key);
    else it.run?.();
  }

  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="palette" onClick={(e) => e.stopPropagation()}>
        <input
          autoFocus
          placeholder={mode === "files" ? "Go to file…" : "Run a command…"}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") setSel((s) => Math.min(s + 1, items.length - 1));
            else if (e.key === "ArrowUp") setSel((s) => Math.max(s - 1, 0));
            else if (e.key === "Enter") choose(sel);
            else if (e.key === "Escape") onClose();
          }}
        />
        <div className="palette-list" ref={listRef}>
          {items.map((it, i) => (
            <div key={it.key} className={`palette-row ${i === sel ? "sel" : ""}`} onClick={() => choose(i)}>
              <span className="pl-label">{it.label}</span>
              {(it as any).hint && <span className="pl-hint">{(it as any).hint}</span>}
            </div>
          ))}
          {items.length === 0 && <div className="muted pad">No results.</div>}
        </div>
      </div>
    </div>
  );
}
