import { useNavigate } from "react-router-dom";
import { api } from "@/api/client";
import { useApi, useAction } from "@/api/hooks";
import type { Overview as OverviewData, ReadingItem } from "@/api/types";
import { Disclaimer } from "@/components/Analysis";
import { Donut } from "@/components/Charts";
import { Icon } from "@/components/Icon";
import { PaperJob } from "@/components/Job";
import { Boundary, OllamaBanner } from "@/components/states";
import { Button, EmptyState, PageTitle, Pill, Switch } from "@/components/ui";
import { useApp, useProjectId } from "@/context/AppContext";
import { delta, greeting, paperLabel, pct, pluralize, projectMark, relativeTime, today, viewerLink } from "@/lib/format";

const MARKS = ["", "project-mark--blue", "project-mark--sand"];

function Dashboard({ data, reading }: { data: OverviewData; reading: ReadingItem[] }) {
  const nav = useNavigate();
  const { userName, projects, project, refreshProjects, toast, settings } = useApp();
  const toggle = useAction(async (v: boolean) => {
    await api.patch(`/projects/${data.project.id}`, { think_first: v });
    await refreshProjects();
    toast(v ? "Think-first is on for this project" : "Think-first is off for this project");
  });

  const { stats, index, extraction_health: h } = data;
  const indexPct = index.chunks ? Math.round((index.embedded / index.chunks) * 100) : 0;
  const review = stats.awaiting_review;
  const first = userName.split(" ")[0];
  const last = data.evaluation[data.evaluation.length - 1]?.metrics;
  const prev = data.evaluation[data.evaluation.length - 2]?.metrics;
  const unread = reading.filter((r) => r.status !== "read").length;
  const extractionTotal = h.agree + h.verify + h.confirmed;

  return (
    <div className="screen">
      <PageTitle
        eyebrow={today()}
        title={`${greeting()}${first ? `, ${first}` : ""}`}
        description={stats.papers === 0
          ? "Your workspace is empty. Add a few papers and they will be indexed on this device."
          : review > 0 ? `${pluralize(review, "extracted field")} ${review === 1 ? "is" : "are"} waiting for your review.` : "Everything extracted so far has been reviewed."}
        actions={<>
          <label className="switch-label">Think-first mode
            <Switch checked={data.project.think_first} onChange={(v) => void toggle.run(v)} label="Think-first mode" disabled={toggle.busy} />
          </label>
          <Button variant="primary" icon="plus" onClick={() => nav("/upload")}>Add papers</Button>
        </>}
      />
      <OllamaBanner />

      <div className="metric-grid">
        <div className="metric"><span>Library</span><strong>{stats.papers}</strong><small>{stats.pages} pages indexed</small></div>
        <div className="metric"><span>Needs review</span><strong>{review}</strong><small>{stats.fields_extracted} fields extracted</small></div>
        <div className="metric"><span>Reading list</span><strong>{reading.length}</strong><small>{unread} not yet read</small></div>
        <div className="metric metric--accent"><span>Local index</span><strong>{index.chunks ? `${indexPct}%` : "n/a"}</strong>
          <small><i /> {index.embedded}/{index.chunks} passages embedded</small></div>
      </div>

      <div className="dashboard-grid">
        <section className="panel panel--span2">
          <div className="section-head"><div><h2>Continue your work</h2><p>{data.recent_thread ? `Last thread: ${data.recent_thread.title}` : "Your projects"}</p></div>
            <Button variant="ghost" onClick={() => nav("/projects")}>View all <Icon name="arrow" size={14} /></Button></div>
          {data.recent_thread && (
            <div className="project-row" role="button" tabIndex={0} onClick={() => nav(`/threads/${data.recent_thread?.id}`)}
              onKeyDown={(e) => { if (e.key === "Enter") nav(`/threads/${data.recent_thread?.id}`); }}>
              <div className="project-mark"><Icon name="thread" size={16} /></div>
              <div><b>{data.recent_thread.title}</b><span>Most recent thread · {relativeTime(data.recent_thread.updated_at)}</span></div>
              <div />
              <Icon name="chevron" />
            </div>
          )}
          {projects.slice(0, 3).map((p, i) => (
            <div className="project-row" key={p.id} role="button" tabIndex={0} onClick={() => nav(`/projects/${p.id}`)}
              onKeyDown={(e) => { if (e.key === "Enter") nav(`/projects/${p.id}`); }}>
              <div className={`project-mark ${MARKS[i % 3]}`}>{projectMark(p.name)}</div>
              <div><b>{p.name}</b><span>{pluralize(p.paper_count, "paper")} · {pluralize(p.thread_count, "thread")} · edited {relativeTime(p.updated_at)}</span></div>
              {p.id === project?.id && extractionTotal > 0
                ? <div className="project-progress"><span>Fields reviewed</span><div className="progress"><i style={{ width: `${Math.round((h.confirmed / extractionTotal) * 100)}%` }} /></div></div>
                : <div />}
              <Icon name="chevron" />
            </div>
          ))}
        </section>

        <section className="panel">
          <div className="section-head"><div><h2>Processing</h2><p>Runs locally on this device</p></div></div>
          {data.jobs.length === 0 && <p className="muted" style={{ fontSize: 11 }}>Nothing is processing right now.</p>}
          {data.jobs.slice(0, 3).map((j) => <PaperJob key={j.id} paper={j} />)}
          <Button variant="ghost" onClick={() => nav("/upload")}>Open processing queue <Icon name="arrow" size={14} /></Button>
        </section>

        <section className="panel panel--span2">
          <div className="section-head"><div><h2>Decision log alerts</h2><p>New evidence related to recorded decisions</p></div>
            {data.alerts.length > 0 && <Pill tone="amber">{data.alerts.length} need review</Pill>}</div>
          {data.alerts.length === 0 && <p className="muted" style={{ fontSize: 11 }}>No conflicts. When a new paper reports something that differs from a logged decision, it shows up here with the quote.</p>}
          {data.alerts.map((a) => (
            <div className="alert-row" key={a.id}>
              <span className="alert-dot">!</span>
              <div><b>{a.message}</b><p>“{a.quote.quote}” · {a.quote.label}{a.quote.page ? `, p. ${a.quote.page}` : ""}</p><span>Linked decision: {a.decision_title}</span></div>
              <Button onClick={() => nav("/decisions")}>Review evidence</Button>
            </div>
          ))}
        </section>

        <section className="panel">
          <div className="section-head"><div><h2>Reading list</h2><p>{reading.length} saved · {unread} unread</p></div></div>
          {reading.length === 0 && <p className="muted" style={{ fontSize: 11 }}>Papers you save from Find references appear here.</p>}
          {reading.slice(0, 3).map((p) => <div className="mini-paper" key={p.id}><span>{p.title}</span><small>{paperLabel(p.authors, p.year)}</small></div>)}
          <Button variant="ghost" onClick={() => nav("/reading")}>Open reading list <Icon name="arrow" size={14} /></Button>
        </section>

        <section className="panel panel--span2">
          <div className="section-head"><div><h2>Contradictions snapshot</h2><p>{data.contradiction_total} candidate {data.contradiction_total === 1 ? "conflict" : "conflicts"} at your tolerance of {settings?.tolerance ?? 5}%</p></div>
            <Button variant="ghost" onClick={() => nav("/contradictions")}>Open view <Icon name="arrow" size={14} /></Button></div>
          {data.contradictions.length === 0 && <p className="muted" style={{ fontSize: 11 }}>No pairs where method, dataset and metric match but values differ. Review extracted fields to enable comparisons.</p>}
          {data.contradictions.map((c) => (
            <div className="mini-paper" key={c.n} role="button" tabIndex={0} style={{ cursor: "pointer" }}
              onClick={() => nav("/contradictions")} onKeyDown={(e) => { if (e.key === "Enter") nav("/contradictions"); }}>
              <span>{c.title}</span>
              <small>{c.a.label}: {c.a.display} · {c.b.label}: {c.b.display} · differ by {c.relative_difference_pct.toFixed(1)}%</small>
            </div>
          ))}
        </section>

        <section className="panel">
          <div className="section-head"><div><h2>Extraction health</h2><p>Agreement across two passes</p></div></div>
          <Donut caption="reviewed" centre={extractionTotal ? pct(h.confirmed / extractionTotal) : "n/a"}
            segments={[{ value: h.confirmed, color: "var(--accent)", label: "confirmed" }, { value: h.agree, color: "var(--blue)", label: "passes agree" }, { value: h.verify, color: "var(--amber)", label: "verify manually" }]} />
          <ul className="legend"><li><i className="teal" />{h.confirmed} confirmed</li><li><i />{h.agree} both passes agree</li><li><i className="amber" />{h.verify} verify manually</li></ul>
        </section>

        <section className="panel panel--span2">
          <div className="section-head"><div><h2>Evaluation snapshot</h2><p>{last ? `${last.answerable + last.unanswerable} questions · k=${last.k}` : "No evaluation run yet"}</p></div>
            <Button variant="ghost" onClick={() => nav("/evaluation")}>Open evaluation <Icon name="arrow" size={14} /></Button></div>
          {last ? (
            <div className="eval-metrics" style={{ marginBottom: 0 }}>
              <div className="metric"><span>Recall@{last.k}</span><strong>{pct(last.recall_at_k)}</strong><small>{delta(last.recall_at_k, prev?.recall_at_k, true) ?? ""}</small></div>
              <div className="metric"><span>MRR</span><strong>{last.mrr?.toFixed(2) ?? "n/a"}</strong><small>{delta(last.mrr, prev?.mrr) ?? ""}</small></div>
              <div className="metric"><span>Faithfulness</span><strong>{pct(last.citation_faithfulness)}</strong><small>{delta(last.citation_faithfulness, prev?.citation_faithfulness, true) ?? ""}</small></div>
              <div className="metric"><span>Refusal accuracy</span><strong>{pct(last.refusal_accuracy)}</strong><small>{delta(last.refusal_accuracy, prev?.refusal_accuracy, true) ?? ""}</small></div>
            </div>
          ) : <p className="muted" style={{ fontSize: 11 }}>Run the evaluation to measure retrieval quality, citation grounding and appropriate refusal.</p>}
        </section>

        <section className="panel">
          <div className="section-head"><div><h2>Candidate gaps</h2><p>For you to evaluate</p></div></div>
          {data.gaps.length === 0 && <p className="muted" style={{ fontSize: 11 }}>Appears once your papers contain limitations or future-work statements.</p>}
          {data.gaps.map((g) => <div className="mini-paper" key={g.n}><span>{g.label}</span><small>{pluralize(g.paper_count, "paper")} · {pluralize(g.statement_count, "statement")}</small></div>)}
          <Button variant="ghost" onClick={() => nav("/gaps")}>Open gap map <Icon name="arrow" size={14} /></Button>
        </section>

        <section className="panel panel--span2">
          <div className="section-head"><div><h2>Quick actions</h2><p>Jump into the common workflows</p></div></div>
          <div className="queue-actions">
            <Button icon="upload" onClick={() => nav("/upload")}>Upload papers</Button>
            <Button icon="search" onClick={() => nav("/references")}>Find references</Button>
            <Button icon="file" onClick={() => nav("/diff")}>Compare papers</Button>
            <Button icon="thread" variant="primary" onClick={() => nav("/threads")}>Ask your papers</Button>
          </div>
          {data.recent_papers[0] && <p className="muted" style={{ fontSize: 11, marginTop: 12 }}>Latest paper: <button className="link-button" onClick={() => nav(viewerLink(data.recent_papers[0].id))}>{data.recent_papers[0].title}</button></p>}
        </section>

        <section className="panel">
          <div className="section-head"><div><h2>Privacy status</h2><p>What stays on this device</p></div><Disclaimer text="Local-first" /></div>
          <div className="mini-paper"><span>Answer model</span><small>{data.privacy.answer_model} · runs locally</small></div>
          <div className="mini-paper"><span>Embedding model</span><small>{data.privacy.embed_model} · runs locally</small></div>
          <div className="mini-paper"><span>Online discovery</span><small>{data.privacy.online_discovery ? "On: short search queries may be sent to scholarly indexes" : "Off: nothing leaves this device"}</small></div>
          <Button variant="ghost" onClick={() => nav("/settings")}>Review privacy settings <Icon name="arrow" size={14} /></Button>
        </section>
      </div>
    </div>
  );
}

export default function Overview() {
  const pid = useProjectId();
  const { projects, activeJobs } = useApp();
  const res = useApi((s) => api.get<OverviewData>(`/projects/${pid}/overview`, s), [pid, projects.length, activeJobs], pid > 0);
  const reading = useApi((s) => api.get<ReadingItem[]>(`/projects/${pid}/reading`, s), [pid], pid > 0);
  return (
    <Boundary res={res} empty={() => (pid ? null : <EmptyState title="No project yet" text="Create a project to begin." />)}>
      {(data) => <Dashboard data={data} reading={reading.data ?? []} />}
    </Boundary>
  );
}
