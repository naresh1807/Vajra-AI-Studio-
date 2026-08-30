/** Line-level diff → hunks, so Assisted edits can be applied one hunk at a time
 *  (manual v3.0 PRIORITY 10 — never force a whole-file accept/reject). */

export interface Hunk {
  /** 0-based line range in the ORIGINAL that this hunk replaces (end exclusive). */
  origStart: number;
  origEnd: number;
  /** replacement lines (already newline-free). */
  replacement: string[];
  /** context for the picker. */
  removed: string[];
  added: string[];
}

/** Longest-common-subsequence over lines → a minimal set of replace hunks. */
export function diffHunks(original: string, proposed: string): Hunk[] {
  const a = splitLines(original);
  const b = splitLines(proposed);
  const n = a.length;
  const m = b.length;

  // LCS length table.
  const lcs: number[][] = Array.from({ length: n + 1 }, () => new Array(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--)
    for (let j = m - 1; j >= 0; j--)
      lcs[i][j] = a[i] === b[j] ? lcs[i + 1][j + 1] + 1 : Math.max(lcs[i + 1][j], lcs[i][j + 1]);

  const hunks: Hunk[] = [];
  let i = 0;
  let j = 0;
  let pendA: string[] = [];
  let pendB: string[] = [];
  let hunkStart = 0;

  const flush = (endI: number) => {
    if (pendA.length || pendB.length) {
      hunks.push({
        origStart: hunkStart,
        origEnd: endI,
        replacement: pendB.slice(),
        removed: pendA.slice(),
        added: pendB.slice(),
      });
    }
    pendA = [];
    pendB = [];
  };

  while (i < n && j < m) {
    if (a[i] === b[j]) {
      flush(i);
      i++;
      j++;
      hunkStart = i;
    } else if (lcs[i + 1][j] >= lcs[i][j + 1]) {
      if (!pendA.length && !pendB.length) hunkStart = i;
      pendA.push(a[i++]);
    } else {
      if (!pendA.length && !pendB.length) hunkStart = i;
      pendB.push(b[j++]);
    }
  }
  if (!pendA.length && !pendB.length) hunkStart = i;
  while (i < n) pendA.push(a[i++]);
  while (j < m) pendB.push(b[j++]);
  flush(n);

  return hunks;
}

function splitLines(text: string): string[] {
  // Keep it newline-agnostic; callers re-join with the document's own EOL.
  return text.split(/\r\n|\r|\n/);
}

/** Apply a subset of hunks to `original`, returning the new full text. */
export function applyHunks(original: string, hunks: Hunk[], selected: Set<number>, eol: string): string {
  const a = splitLines(original);
  const out: string[] = [];
  let cursor = 0;
  hunks.forEach((h, idx) => {
    out.push(...a.slice(cursor, h.origStart));
    out.push(...(selected.has(idx) ? h.replacement : a.slice(h.origStart, h.origEnd)));
    cursor = h.origEnd;
  });
  out.push(...a.slice(cursor));
  return out.join(eol);
}
