import { useSearchParams } from "react-router-dom";
import { api } from "@/api/client";
import { useApi } from "@/api/hooks";
import type { Paper } from "@/api/types";
import { useProjectId } from "@/context/AppContext";
import { paperLabel } from "@/lib/format";

/** Papers in the current project that finished processing (analyses need their text). */
export function useProjectPapers() {
  const pid = useProjectId();
  const res = useApi((s) => api.get<Paper[]>(`/papers?project_id=${pid}`, s), [pid], pid > 0);
  const ready = (res.data ?? []).filter((p) => p.status === "ready" || p.status === "ready_keyword_only");
  return { res, ready, pid };
}

export const labelOf = (p: Paper): string => paperLabel(p.authors, p.year, p.title);

/** One paper, kept in the URL (?paper=ID) so analysis pages can be linked and survive a reload. */
export function usePaperParam(papers: Paper[]): [number | null, (id: number) => void] {
  const [sp, setSp] = useSearchParams();
  const raw = Number(sp.get("paper"));
  const chosen = papers.find((p) => p.id === raw)?.id ?? papers[0]?.id ?? null;
  return [chosen, (id) => setSp({ paper: String(id) }, { replace: true })];
}

export function PaperSelect({
  papers, value, onChange, label = "Paper",
}: { papers: Paper[]; value: number | null; onChange: (id: number) => void; label?: string }) {
  return (
    <label className="field">
      <span>{label}</span>
      <select value={value ?? ""} onChange={(e) => onChange(Number(e.target.value))} aria-label={label}>
        {papers.map((p) => <option key={p.id} value={p.id}>{labelOf(p)} · {p.title.length > 60 ? `${p.title.slice(0, 60)}…` : p.title}</option>)}
      </select>
    </label>
  );
}

/** Pick several papers (used by Paper Diff and the Prediction Gate). */
export function PaperChecklist({
  papers, selected, onChange, max = 6,
}: { papers: Paper[]; selected: number[]; onChange: (ids: number[]) => void; max?: number }) {
  const toggle = (id: number) => {
    if (selected.includes(id)) onChange(selected.filter((x) => x !== id));
    else if (selected.length < max) onChange([...selected, id]);
  };
  return (
    <div className="diff-pickers" role="group" aria-label="Choose papers">
      {papers.map((p, i) => {
        const on = selected.includes(p.id);
        return (
          <label key={p.id} style={{ cursor: "pointer", outline: on ? "2px solid var(--accent)" : undefined }}>
            <input type="checkbox" className="sr-only" checked={on} onChange={() => toggle(p.id)} aria-label={p.title} />
            <span className={`project-mark p${i % 3}`}>{on ? selected.indexOf(p.id) + 1 : "·"}</span>
            <div><small>{on ? `PAPER ${selected.indexOf(p.id) + 1}` : "ADD"}</small><b>{p.title}</b><span>{labelOf(p)}</span></div>
          </label>
        );
      })}
    </div>
  );
}

export function downloadText(filename: string, text: string, type = "text/plain"): void {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}
