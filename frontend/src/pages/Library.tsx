import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/api/client";
import { useAction, useApi } from "@/api/hooks";
import type { Paper } from "@/api/types";
import { Icon } from "@/components/Icon";
import { Boundary, SkeletonCards } from "@/components/states";
import { Button, EmptyState, IconButton, Modal, PageTitle, Pill } from "@/components/ui";
import { useApp, useProjectId } from "@/context/AppContext";
import { paperStatusLabel, pluralize } from "@/lib/format";

export default function Library() {
  const nav = useNavigate();
  const pid = useProjectId();
  const { project, toast, refreshProjects, refreshJobs } = useApp();
  const res = useApi((s) => api.get<Paper[]>(`/papers?project_id=${pid}`, s), [pid], pid > 0);
  const [grid, setGrid] = useState(false);
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [year, setYear] = useState("");
  const [picked, setPicked] = useState<number[]>([]);
  const [confirm, setConfirm] = useState<Paper[] | null>(null);

  const remove = useAction(async (papers: Paper[]) => {
    for (const p of papers) await api.del(`/papers/${p.id}`);
    toast(`Deleted ${pluralize(papers.length, "paper")}`);
    setPicked([]);
    setConfirm(null);
    res.reload();
    void refreshProjects();
    refreshJobs();
  });
  const reindex = useAction(async (ids: number[]) => {
    for (const id of ids) await api.post(`/papers/${id}/reindex`);
    toast(`Re-indexing ${pluralize(ids.length, "paper")}`);
    setPicked([]);
    res.reload();
    refreshJobs();
  });
  const exportAll = useAction(() => api.download("/data/export", "researchmind-export.zip", "POST"));

  const papers = res.data ?? [];
  const years = useMemo(() => [...new Set(papers.map((p) => p.year).filter((y): y is number => y !== null))].sort((a, b) => b - a), [papers]);
  const shown = papers.filter((p) => {
    const hay = `${p.title} ${p.authors} ${p.venue}`.toLowerCase();
    if (q && !hay.includes(q.toLowerCase())) return false;
    if (status === "processing" && p.job_state !== "running" && p.job_state !== "queued") return false;
    if (status === "ready" && p.job_state !== "done") return false;
    if (status === "failed" && p.job_state !== "failed") return false;
    if (year && String(p.year) !== year) return false;
    return true;
  });
  const toggle = (id: number) => setPicked((c) => (c.includes(id) ? c.filter((x) => x !== id) : [...c, id]));
  const allPicked = shown.length > 0 && shown.every((p) => picked.includes(p.id));

  return (
    <div className="screen">
      <PageTitle title="Papers" description={`${pluralize(papers.length, "paper")} indexed locally in ${project?.name ?? "this project"}.`}
        actions={<>
          <Button icon="download" onClick={() => void exportAll.run()} disabled={exportAll.busy} title="Downloads the whole workspace: data and original PDFs">Export workspace</Button>
          <Button variant="primary" icon="upload" onClick={() => nav("/upload")}>Upload papers</Button>
        </>} />
      <div className="toolbar">
        <div className="field field--search"><Icon name="search" size={16} /><input aria-label="Filter papers" placeholder="Filter by title, author, venue…" value={q} onChange={(e) => setQ(e.target.value)} /></div>
        <select className="select-like" aria-label="Status" value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">Any status</option><option value="ready">Indexed</option><option value="processing">Processing</option><option value="failed">Needs attention</option>
        </select>
        <select className="select-like" aria-label="Year" value={year} onChange={(e) => setYear(e.target.value)}>
          <option value="">Any year</option>{years.map((y) => <option key={y} value={y}>{y}</option>)}
        </select>
        <div className="view-toggle"><IconButton icon="list" label="List view" onClick={() => setGrid(false)} /><IconButton icon="grid" label="Grid view" onClick={() => setGrid(true)} /></div>
      </div>

      <Boundary res={res} skeleton={<SkeletonCards n={4} />}
        empty={(d) => d.length === 0 ? <EmptyState icon="upload" title="No papers yet" text="Upload PDFs and ResearchMind will extract the text, build a local index and read each paper's setup fields." action={<Button variant="primary" onClick={() => nav("/upload")}>Upload papers</Button>} /> : null}>
        {() => (
          <>
            <div className="bulk-bar">
              <label><input type="checkbox" checked={allPicked} onChange={() => setPicked(allPicked ? [] : shown.map((p) => p.id))} /> Select all</label>
              <span>{picked.length ? `${picked.length} selected` : `${shown.length} shown`}</span>
              <div>
                <Button variant="ghost" disabled={!picked.length || reindex.busy} onClick={() => void reindex.run(picked)}>Re-index</Button>
                <Button variant="ghost" disabled={!picked.length} onClick={() => setConfirm(papers.filter((p) => picked.includes(p.id)))}>Delete</Button>
              </div>
            </div>
            {shown.length === 0 && <EmptyState icon="search" title="No papers match" text="Clear the filters to see everything in this project." />}
            <div className={grid ? "paper-grid" : "paper-list"}>
              {shown.map((p) => {
                const st = paperStatusLabel(p.status);
                return (
                  <article className="paper-card" key={p.id} onClick={() => nav(`/papers/${p.id}`)}>
                    <div className="paper-card__select"><input type="checkbox" aria-label={`Select ${p.title}`} checked={picked.includes(p.id)} onClick={(e) => e.stopPropagation()} onChange={() => toggle(p.id)} /></div>
                    <div className="paper-thumb"><span>{p.venue || "PDF"}</span><b>{p.title.split(" ").slice(0, 3).join(" ")}</b><small>{p.year ?? ""}</small></div>
                    <div className="paper-card__content">
                      <div className="paper-card__meta"><Pill tone={st.tone}>{st.label}</Pill></div>
                      <h3>{p.title}</h3>
                      <p>{[p.authors, p.venue, p.year].filter(Boolean).join(" · ") || p.filename}</p>
                      <small>{p.page_count} pages · {p.chunk_count} passages</small>
                    </div>
                    <IconButton icon="trash" label={`Delete ${p.title}`} onClick={() => setConfirm([p])} />
                  </article>
                );
              })}
            </div>
          </>
        )}
      </Boundary>

      {confirm && (
        <Modal title={`Delete ${pluralize(confirm.length, "paper")}?`} onClose={() => setConfirm(null)}
          actions={<><Button onClick={() => setConfirm(null)}>Cancel</Button><Button variant="danger" disabled={remove.busy} onClick={() => void remove.run(confirm)}>Delete permanently</Button></>}>
          <p>The PDF, its extracted text, index entries and extracted fields are removed from this device. Threads that cited it keep their text, but the passages can no longer be opened.</p>
          {remove.error && <p className="form-error" role="alert">{remove.error}</p>}
        </Modal>
      )}
    </div>
  );
}
