import { useEffect, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api } from "@/api/client";
import { useAction, useApi } from "@/api/hooks";
import type { Decision, Overview, Paper, ProvDoc, Thread } from "@/api/types";
import { Donut } from "@/components/Charts";
import { Icon } from "@/components/Icon";
import { Boundary, SkeletonCards } from "@/components/states";
import { Button, EmptyState, IconButton, Modal, PageTitle, Pill } from "@/components/ui";
import { useApp } from "@/context/AppContext";
import { pluralize, projectMark, relativeTime } from "@/lib/format";

function ProjectForm({ initial, title, submitLabel, onDone, onClose }: {
  initial?: { name: string; question: string }; title: string; submitLabel: string;
  onDone: (v: { name: string; question: string }) => Promise<unknown>; onClose: () => void;
}) {
  const [name, setName] = useState(initial?.name ?? "");
  const [question, setQuestion] = useState(initial?.question ?? "");
  const save = useAction(async () => { await onDone({ name: name.trim(), question: question.trim() }); onClose(); });
  return (
    <Modal title={title} onClose={onClose}
      actions={<><Button onClick={onClose}>Cancel</Button><Button variant="primary" disabled={save.busy || !name.trim()} onClick={() => void save.run()}>{submitLabel}</Button></>}>
      <label>Name<input autoFocus value={name} onChange={(e) => setName(e.target.value)} maxLength={200} /></label>
      <label>Research question <span className="muted">(optional)</span>
        <textarea value={question} onChange={(e) => setQuestion(e.target.value)} maxLength={2000} placeholder="What are you trying to find out?" /></label>
      {save.error && <p className="form-error" role="alert">{save.error}</p>}
    </Modal>
  );
}

export function Projects() {
  const nav = useNavigate();
  const [sp, setSp] = useSearchParams();
  const { projects, refreshProjects, selectProject, toast } = useApp();
  const [creating, setCreating] = useState(sp.get("new") === "1");
  const [doomed, setDoomed] = useState<number | null>(null);
  useEffect(() => { if (sp.get("new") === "1") setCreating(true); }, [sp]);

  const closeCreate = () => { setCreating(false); if (sp.has("new")) { sp.delete("new"); setSp(sp, { replace: true }); } };
  const remove = useAction(async (id: number) => {
    await api.del(`/projects/${id}`);
    setDoomed(null);
    await refreshProjects();
    toast("Project deleted");
  });
  const doomedProject = projects.find((p) => p.id === doomed);

  return (
    <div className="screen">
      <PageTitle title="Projects" description="Organize papers, threads, notes, and decisions around a research question."
        actions={<Button variant="primary" icon="plus" onClick={() => setCreating(true)}>New project</Button>} />
      {projects.length === 0 && <EmptyState icon="folder" title="No projects yet" text="Create one to start adding papers." action={<Button variant="primary" onClick={() => setCreating(true)}>New project</Button>} />}
      <div className="project-grid">
        {projects.map((p, i) => (
          <article className="project-card" key={p.id} onClick={() => { selectProject(p.id); nav(`/projects/${p.id}`); }}>
            <div className={`project-mark p${i % 4}`}>{projectMark(p.name)}</div>
            <IconButton icon="trash" label={`Delete ${p.name}`} onClick={() => setDoomed(p.id)} />
            <h2>{p.name}</h2>
            <p>{p.question || "No research question yet."}</p>
            <div className="project-card__stats"><span><b>{p.paper_count}</b> papers</span><span><b>{p.thread_count}</b> threads</span></div>
            <div className="project-card__foot"><span>Edited {relativeTime(p.updated_at)}</span>{p.think_first && <Pill tone="teal">Think-first</Pill>}</div>
          </article>
        ))}
      </div>
      {creating && (
        <ProjectForm title="New project" submitLabel="Create project" onClose={closeCreate}
          onDone={async (v) => {
            const created = await api.post<{ id: number }>("/projects", v);
            await refreshProjects();
            selectProject(created.id);
            nav(`/projects/${created.id}`);
          }} />
      )}
      {doomedProject && (
        <Modal title={`Delete “${doomedProject.name}”?`} onClose={() => setDoomed(null)}
          actions={<><Button onClick={() => setDoomed(null)}>Cancel</Button><Button variant="danger" disabled={remove.busy} onClick={() => void remove.run(doomedProject.id)}>Delete project</Button></>}>
          <p>This removes its {pluralize(doomedProject.paper_count, "paper")}, {pluralize(doomedProject.thread_count, "thread")}, decisions, notes and reading list from this device. It cannot be undone.</p>
          {remove.error && <p className="form-error" role="alert">{remove.error}</p>}
        </Modal>
      )}
    </div>
  );
}

type Tab = "overview" | "papers" | "threads" | "decisions" | "notes";

export function ProjectDetail() {
  const { id } = useParams();
  const pid = Number(id);
  const nav = useNavigate();
  const { projects, refreshProjects, selectProject, toast } = useApp();
  const project = projects.find((p) => p.id === pid);
  const [tab, setTab] = useState<Tab>("overview");
  const [editing, setEditing] = useState(false);
  useEffect(() => { if (project) selectProject(project.id); }, [project, selectProject]);

  const overview = useApi((s) => api.get<Overview>(`/projects/${pid}/overview`, s), [pid], !!project);
  const papers = useApi((s) => api.get<Paper[]>(`/papers?project_id=${pid}`, s), [pid], tab === "papers");
  const threads = useApi((s) => api.get<Thread[]>(`/threads?project_id=${pid}`, s), [pid], tab === "threads");
  const decisions = useApi((s) => api.get<Decision[]>(`/projects/${pid}/decisions`, s), [pid], tab === "decisions");
  const notes = useApi((s) => api.get<ProvDoc[]>(`/projects/${pid}/provenance`, s), [pid], tab === "notes");

  if (!project) return <div className="screen"><EmptyState icon="folder" title="Project not found" text="It may have been deleted." action={<Button onClick={() => nav("/projects")}>All projects</Button>} /></div>;

  const tabs: [Tab, string, number | null][] = [["overview", "Overview", null], ["papers", "Papers", project.paper_count], ["threads", "Threads", project.thread_count], ["decisions", "Decisions", null], ["notes", "Notes", null]];

  return (
    <div className="screen">
      <PageTitle eyebrow="Project" title={project.name} description={project.question || "No research question yet. Add one so your work stays anchored."}
        actions={<><Button icon="settings" onClick={() => setEditing(true)}>Edit project</Button><Button variant="primary" icon="plus" onClick={() => nav("/upload")}>Add papers</Button></>} />
      <div className="tabbar" role="tablist">
        {tabs.map(([k, label, n]) => (
          <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? "active" : ""} onClick={() => setTab(k)}>{label}{n !== null && <> <span>{n}</span></>}</button>
        ))}
      </div>

      {tab === "overview" && (
        <Boundary res={overview}>
          {(o) => {
            const h = o.extraction_health;
            const total = h.agree + h.verify + h.confirmed;
            const next: { text: string; to: string }[] = [];
            if (o.stats.papers === 0) next.push({ text: "Add the first papers to this project", to: "/upload" });
            if (h.verify > 0) next.push({ text: `${pluralize(h.verify, "extracted field")} need your review`, to: "/extraction" });
            if (o.contradiction_total > 0) next.push({ text: `${pluralize(o.contradiction_total, "candidate conflict")} between papers to inspect`, to: "/contradictions" });
            if (o.alerts.length > 0) next.push({ text: `${pluralize(o.alerts.length, "decision")} may conflict with new evidence`, to: "/decisions" });
            if (o.stats.papers > 1 && o.stats.awaiting_review === 0 && next.length === 0) next.push({ text: "Compare two papers' setups side by side", to: "/diff" });
            return (
              <div className="dashboard-grid">
                <section className="panel panel--span2">
                  <div className="section-head"><div><h2>Research question</h2><p>{project.question ? "Your own words" : "Not set yet"}</p></div><Button onClick={() => setEditing(true)}>Edit</Button></div>
                  <div className="research-question">{project.question || "Write the question this project is trying to answer."}</div>
                  <div className="chip-row"><Pill tone={project.think_first ? "teal" : "neutral"}>{project.think_first ? "Think-first on" : "Think-first off"}</Pill></div>
                </section>
                <section className="panel">
                  <div className="section-head"><div><h2>Project health</h2><p>Extraction review</p></div></div>
                  <Donut caption="reviewed" centre={total ? `${Math.round((h.confirmed / total) * 100)}%` : "n/a"}
                    segments={[{ value: h.confirmed, color: "var(--accent)", label: "reviewed" }, { value: h.agree, color: "var(--blue)", label: "agree" }, { value: h.verify, color: "var(--amber)", label: "need review" }]} />
                  <ul className="legend"><li><i className="teal" />{h.confirmed} reviewed</li><li><i className="amber" />{h.verify} need review</li><li><i />{o.jobs.length} processing</li></ul>
                </section>
                <section className="panel panel--span2">
                  <div className="section-head"><div><h2>Recent papers</h2><p>Latest additions</p></div><Button variant="ghost" onClick={() => nav("/papers")}>All papers <Icon name="arrow" size={14} /></Button></div>
                  {o.recent_papers.length === 0 && <p className="muted" style={{ fontSize: 11 }}>No papers yet.</p>}
                  {o.recent_papers.map((p) => <div className="mini-paper" key={p.id} role="button" tabIndex={0} style={{ cursor: "pointer" }} onClick={() => nav(`/papers/${p.id}`)} onKeyDown={(e) => { if (e.key === "Enter") nav(`/papers/${p.id}`); }}><span>{p.title}</span><small>{[p.authors, p.year].filter(Boolean).join(" · ") || p.filename}</small></div>)}
                </section>
                <section className="panel">
                  <div className="section-head"><div><h2>Suggested next steps</h2><p>Based on what is in this project</p></div></div>
                  {next.length === 0 ? <p className="muted" style={{ fontSize: 11 }}>Nothing is waiting on you.</p> : <ol className="question-list">{next.map((n) => <li key={n.text}><button className="link-button" onClick={() => nav(n.to)}>{n.text}</button></li>)}</ol>}
                  <Button variant="ghost" onClick={() => nav("/threads")}>Start a thread <Icon name="arrow" size={14} /></Button>
                </section>
              </div>
            );
          }}
        </Boundary>
      )}

      {tab === "papers" && (
        <Boundary res={papers} skeleton={<SkeletonCards />} empty={(d) => d.length === 0 ? <EmptyState icon="upload" title="No papers" text="Add PDFs to this project." action={<Button variant="primary" onClick={() => nav("/upload")}>Add papers</Button>} /> : null}>
          {(d) => <section className="panel">{d.map((p) => <div className="mini-paper" key={p.id} role="button" tabIndex={0} style={{ cursor: "pointer" }} onClick={() => nav(`/papers/${p.id}`)} onKeyDown={(e) => { if (e.key === "Enter") nav(`/papers/${p.id}`); }}><span>{p.title}</span><small>{[p.authors, p.year, `${p.page_count} pages`].filter(Boolean).join(" · ")}</small></div>)}</section>}
        </Boundary>
      )}
      {tab === "threads" && (
        <Boundary res={threads} skeleton={<SkeletonCards />} empty={(d) => d.length === 0 ? <EmptyState icon="thread" title="No threads yet" text="Ask a question about this project's papers." action={<Button variant="primary" onClick={() => nav("/threads")}>Open threads</Button>} /> : null}>
          {(d) => <section className="panel">{d.map((t) => <div className="mini-paper" key={t.id} role="button" tabIndex={0} style={{ cursor: "pointer" }} onClick={() => nav(`/threads/${t.id}`)} onKeyDown={(e) => { if (e.key === "Enter") nav(`/threads/${t.id}`); }}><span>{t.title}</span><small>{pluralize(t.message_count, "message")} · {relativeTime(t.updated_at)}</small></div>)}</section>}
        </Boundary>
      )}
      {tab === "decisions" && (
        <Boundary res={decisions} skeleton={<SkeletonCards />} empty={(d) => d.length === 0 ? <EmptyState icon="clock" title="No decisions recorded" text="Record choices with their evidence so you hear about it when new work disagrees." action={<Button variant="primary" onClick={() => nav("/decisions")}>Open decision log</Button>} /> : null}>
          {(d) => <section className="panel">{d.map((x) => <div className="mini-paper" key={x.id}><span>{x.title}</span><small>{x.open_alerts > 0 ? `${pluralize(x.open_alerts, "open alert")} · ` : ""}{pluralize(x.evidence.length, "linked passage")}</small></div>)}<Button variant="ghost" onClick={() => nav("/decisions")}>Open decision log <Icon name="arrow" size={14} /></Button></section>}
        </Boundary>
      )}
      {tab === "notes" && (
        <Boundary res={notes} skeleton={<SkeletonCards />} empty={(d) => d.length === 0 ? <EmptyState icon="file" title="No notes yet" text="Notes live in the provenance log, where you can record which passages you used AI assistance on." action={<Button variant="primary" onClick={() => nav("/provenance")}>Open provenance log</Button>} /> : null}>
          {(d) => <section className="panel">{d.map((x) => <div className="mini-paper" key={x.id}><span>{x.title}</span><small>{pluralize(x.words, "word")} · updated {relativeTime(x.updated_at)}</small></div>)}<Button variant="ghost" onClick={() => nav("/provenance")}>Open provenance log <Icon name="arrow" size={14} /></Button></section>}
        </Boundary>
      )}

      {editing && (
        <ProjectForm title="Edit project" submitLabel="Save changes" initial={{ name: project.name, question: project.question }} onClose={() => setEditing(false)}
          onDone={async (v) => { await api.patch(`/projects/${pid}`, v); await refreshProjects(); overview.reload(); toast("Project updated"); }} />
      )}
    </div>
  );
}

