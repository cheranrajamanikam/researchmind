import type { IconName } from "@/components/Icon";

/** One entry per design page id. `path` is the real route; deep links and the back button work. */
export interface NavItem { id: string; path: string; icon: IconName; label: string }
export interface NavGroup { label: string; items: NavItem[] }

export const NAV_GROUPS: NavGroup[] = [
  { label: "Workspace", items: [
    { id: "overview", path: "/", icon: "home", label: "Overview" },
    { id: "library", path: "/papers", icon: "book", label: "Papers" },
    { id: "search", path: "/search", icon: "search", label: "Search" },
    { id: "upload", path: "/upload", icon: "upload", label: "Add papers" },
  ] },
  { label: "Research", items: [
    { id: "projects", path: "/projects", icon: "folder", label: "Projects" },
    { id: "threads", path: "/threads", icon: "thread", label: "Threads" },
  ] },
  { label: "Evaluate", items: [
    { id: "evaluation", path: "/evaluation", icon: "grid", label: "Evaluation" },
    { id: "extraction", path: "/extraction", icon: "list", label: "Extraction review" },
    { id: "diff", path: "/diff", icon: "file", label: "Paper diff" },
    { id: "contradictions", path: "/contradictions", icon: "archive", label: "Contradictions" },
  ] },
  { label: "Discover", items: [
    { id: "references", path: "/references", icon: "search", label: "Find references" },
    { id: "reading", path: "/reading", icon: "book", label: "Reading list" },
    { id: "receipt", path: "/receipts", icon: "file", label: "Search receipts" },
    { id: "prior", path: "/prior-work", icon: "folder", label: "Prior-work audit" },
    { id: "gaps", path: "/gaps", icon: "grid", label: "Gap map" },
  ] },
  { label: "Integrity", items: [
    { id: "numeric", path: "/numeric", icon: "archive", label: "Numeric consistency" },
    { id: "reproducibility", path: "/reproducibility", icon: "check", label: "Reproducibility" },
    { id: "overclaim", path: "/overclaim", icon: "file", label: "Overclaim meter" },
    { id: "audit", path: "/audit", icon: "book", label: "Citation audit" },
  ] },
  { label: "Think first", items: [
    { id: "prediction", path: "/prediction", icon: "help", label: "Prediction gate" },
    { id: "decisions", path: "/decisions", icon: "clock", label: "Decision log" },
    { id: "provenance", path: "/provenance", icon: "file", label: "Provenance log" },
  ] },
];

export function isActive(path: string, pathname: string): boolean {
  if (path === "/") return pathname === "/";
  return pathname === path || pathname.startsWith(`${path}/`);
}
