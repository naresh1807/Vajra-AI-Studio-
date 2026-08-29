import { useState } from "react";
import type { FileNode } from "./api";

function Node({
  node,
  depth,
  activePath,
  onOpen,
}: {
  node: FileNode;
  depth: number;
  activePath: string | null;
  onOpen: (path: string) => void;
}) {
  const [open, setOpen] = useState(depth < 1);
  const pad = { paddingLeft: 8 + depth * 12 };

  if (node.type === "file") {
    return (
      <div
        className={`row file ${activePath === node.path ? "active" : ""}`}
        style={pad}
        onClick={() => onOpen(node.path)}
        title={node.path}
      >
        <span className="ico">·</span>
        {node.name}
      </div>
    );
  }
  return (
    <>
      <div className="row dir" style={pad} onClick={() => setOpen(!open)}>
        <span className="ico">{open ? "▾" : "▸"}</span>
        {node.name || "/"}
      </div>
      {open &&
        node.children?.map((c) => (
          <Node key={c.path} node={c} depth={depth + 1} activePath={activePath} onOpen={onOpen} />
        ))}
    </>
  );
}

export function FileTree({
  tree,
  activePath,
  onOpen,
  onRefresh,
}: {
  tree: FileNode | null;
  activePath: string | null;
  onOpen: (path: string) => void;
  onRefresh: () => void;
}) {
  return (
    <div className="filetree">
      <div className="panel-head">
        <span>Explorer</span>
        <button className="mini" onClick={onRefresh} title="Refresh">
          ⟳
        </button>
      </div>
      <div className="tree-scroll">
        {!tree && <div className="muted pad">Open a folder to start.</div>}
        {tree?.children?.map((c) => (
          <Node key={c.path} node={c} depth={0} activePath={activePath} onOpen={onOpen} />
        ))}
      </div>
    </div>
  );
}
