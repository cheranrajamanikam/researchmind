import type { Citation } from "@/api/types";

/** "Rowan et al. · 2024" / "Rowan · 2024" / "n.d." (mirrors the backend's paper labels). */
export function paperLabel(authors: string, year: number | null, title = ""): string {
  const names = authors.split(/,|;| and /).map((s) => s.trim()).filter(Boolean);
  const y = year ?? "n.d.";
  if (!names.length) return title ? `${title.split(/\s+/).slice(0, 3).join(" ")} · ${y}` : `${y}`;
  const surname = names[0].split(/\s+/).pop() as string;
  return names.length > 1 ? `${surname} et al. · ${y}` : `${surname} · ${y}`;
}

export function citationLabel(c: Pick<Citation, "authors" | "year" | "paper_title">): string {
  return paperLabel(c.authors, c.year, c.paper_title);
}

export function citationText(c: Citation): string {
  const who = c.authors ? `${c.authors} ` : "";
  return `${who}(${c.year ?? "n.d."}). ${c.paper_title}, p. ${c.page}.`;
}

export function relativeTime(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return "";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "";
  const s = Math.max(0, Math.round((now - then) / 1000));
  if (s < 45) return "just now";
  const m = Math.round(s / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h} h ago`;
  const d = Math.round(h / 24);
  if (d === 1) return "yesterday";
  if (d < 30) return `${d} days ago`;
  return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

export function dateTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

export function greeting(now = new Date()): string {
  const h = now.getHours();
  return h < 5 ? "Good evening" : h < 12 ? "Good morning" : h < 18 ? "Good afternoon" : "Good evening";
}

export function today(now = new Date()): string {
  return now.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" });
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "?";
  return (parts.length === 1 ? parts[0].slice(0, 2) : parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export function projectMark(name: string): string {
  return initials(name);
}

export const pct = (v: number | null | undefined, digits = 0): string =>
  v === null || v === undefined ? "n/a" : `${(v * 100).toFixed(digits)}%`;

export const num = (v: number | null | undefined, digits = 2): string =>
  v === null || v === undefined ? "n/a" : v.toFixed(digits);

/** Signed difference between two metric values, formatted for display (e.g. "+0.04"). */
export function delta(cur: number | null | undefined, prev: number | null | undefined, asPct = false): string | null {
  if (cur == null || prev == null) return null;
  const d = cur - prev;
  const s = asPct ? `${(d * 100).toFixed(1)}%` : d.toFixed(2);
  return `${d >= 0 ? "+" : "−"}${s.replace("-", "")}`;
}

export function pluralize(n: number, one: string, many = `${one}s`): string {
  return `${n} ${n === 1 ? one : many}`;
}

/** Link to the viewer with the page and the exact quote to highlight. */
export function viewerLink(paperId: number, page?: number | null, quote?: string): string {
  const q = new URLSearchParams();
  if (page) q.set("page", String(page));
  if (quote) q.set("q", quote.slice(0, 300));
  const qs = q.toString();
  return `/papers/${paperId}${qs ? `?${qs}` : ""}`;
}

export function paperStatusLabel(status: string): { label: string; tone: "neutral" | "teal" | "blue" | "amber" } {
  switch (status) {
    case "ready": return { label: "Indexed", tone: "teal" };
    case "ready_keyword_only": return { label: "Keyword only", tone: "amber" };
    case "extracting": case "chunking": case "embedding": return { label: "Processing", tone: "blue" };
    case "queued": return { label: "Queued", tone: "neutral" };
    case "no_text": return { label: "No text found", tone: "amber" };
    case "failed": return { label: "Failed", tone: "amber" };
    default: return { label: status, tone: "neutral" };
  }
}

export const FIELD_STATUS_LABEL: Record<string, string> = {
  agree: "Both passes agree",
  verify: "Verify manually",
  confirmed: "Confirmed by you",
  edited: "Edited by you",
  rejected: "Rejected by you",
  not_reported: "Not reported",
};
