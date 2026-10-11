import type { ProvMark } from "@/api/types";

export interface Span { start: number; end: number }

/** Keep marks anchored to the same words after the text changes (common prefix / suffix diff). */
export function shiftMarks(prev: string, next: string, marks: Span[]): Span[] {
  if (prev === next) return marks;
  const max = Math.min(prev.length, next.length);
  let p = 0;
  while (p < max && prev[p] === next[p]) p++;
  let s = 0;
  while (s < max - p && prev[prev.length - 1 - s] === next[next.length - 1 - s]) s++;
  const delta = next.length - prev.length;
  const oldEnd = prev.length - s; // end of the edited region in the old text
  const newEnd = next.length - s; // end of the edited region in the new text
  return marks
    .map((m) => ({
      start: m.start <= p ? m.start : m.start >= oldEnd ? m.start + delta : p,
      end: m.end <= p ? m.end : m.end >= oldEnd ? m.end + delta : newEnd,
    }))
    .filter((m) => m.end > m.start && m.start >= 0 && m.end <= next.length);
}

/** Add a span and merge anything it touches, so marks never overlap. */
export function addMark(marks: Span[], span: Span): Span[] {
  let { start, end } = span;
  const keep: Span[] = [];
  for (const m of marks) {
    if (m.end < start || m.start > end) keep.push(m);
    else { start = Math.min(start, m.start); end = Math.max(end, m.end); }
  }
  return [...keep, { start, end }].sort((a, b) => a.start - b.start);
}

/** Remove every mark that overlaps the selection. */
export function removeMarks(marks: Span[], span: Span): Span[] {
  return marks.filter((m) => m.end <= span.start || m.start >= span.end);
}

export function overlaps(marks: Span[], span: Span): boolean {
  return marks.some((m) => m.start < span.end && m.end > span.start);
}

/** Split text into plain and marked runs for display. */
export function segments(text: string, marks: Span[]): { text: string; marked: boolean }[] {
  const out: { text: string; marked: boolean }[] = [];
  let cur = 0;
  for (const m of [...marks].sort((a, b) => a.start - b.start)) {
    if (m.start < cur || m.end > text.length) continue;
    if (m.start > cur) out.push({ text: text.slice(cur, m.start), marked: false });
    out.push({ text: text.slice(m.start, m.end), marked: true });
    cur = m.end;
  }
  if (cur < text.length) out.push({ text: text.slice(cur), marked: false });
  return out;
}

export const wordCount = (s: string): number => (s.trim() ? s.trim().split(/\s+/).length : 0);
export type { ProvMark };
