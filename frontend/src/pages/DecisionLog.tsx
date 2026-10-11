import { useState } from "react";
import { api } from "@/api/client";
import { useAction, useApi } from "@/api/hooks";
import type { Alert, Decision } from "@/api/types";
import { HowComputed } from "@/components/Analysis";
import { EvidenceCard, evidenceFrom } from "@/components/Evidence";
import { labelOf, useProjectPapers } from "@/components/PaperPicker";
import { Boundary } from "@/components/states";
import { Button, EmptyState, IconButton, Modal, PageTitle, Pill } from "@/components/ui";
import { useApp, useProjectId } from "@/context/AppContext";
import { dateTime } from "@/lib/format";

interface Draft { title: string; rationale: string; method: string; dataset: string; metric: string; paper: string; page: string; quote: string }
const EMPTY: Draft = { title: "", rationale: "", method: "", dataset: "", metric: "", paper: "", page: "", quote: "" };

function AlertBlock({ a, onResolve }: { a: Alert; onResolve: () => void }) {
  return (
    <div className="conflict-alert" role="alert">
      <span>!</span>
      <div>
        <b>New paper may conflict with this decision</b>
        <p>{a.message}</p>
        <EvidenceCard compact highlighted c={evidenceFrom(a.quote)} />
        {a.quote.baseline && <EvidenceCard compact c={evidenceFrom(a.quote.baseline)} />}
        <HowComputed label="Why this was flagged" rows={[{ label: "Rule", value: "When a paper finishes processing, its reported result for the same method, dataset and metric is compared with the papers linked to your decision. A difference above your tolerance raises this prompt to re-read both. It is not a finding that the decision was wrong." }]} />
      </div>
      <Button onClick={onResolve}>Mark reviewed</Button>
    </div>
  );
}

export default function DecisionLog() {
  const pid = useProjectId();
  const { toast } = useApp();
  const { ready } = useProjectPapers();
  const res = useApi((s) => api.get<Decision[]>(`/projects/${pid}/decisions`, s), [pid], pid > 0);
  const [filter, setFilter] = useState<"all" | "review">("all");
  const [open, setOpen] = useState(false);
  const [d, setD] = useState<Draft>(EMPTY);

  const create = useAction(async () => {
    const evidence = d.paper && d.quote.trim() ? [{ paper_id: Number(d.paper), page: d.page ? Number(d.page) : null, quote: d.quote.trim() }] : [];
    await api.post(`/projects/${pid}/decisions`, { title: d.title, rationale: d.rationale, method: d.method, dataset: d.dataset, metric: d.metric, evidence });
    setOpen(false);
    setD(EMPTY);
    res.reload();
    toast("Decision recorded");
  });
  const resolve = async (id: number) => {
    try { await api.post(`/alerts/${id}/resolve`); res.reload(); } catch (e) { toast((e as Error).message, "error"); }
  };
  const remove = async (id: number) => {
    try { await api.del(`/decisions/${id}`); res.reload(); } catch (e) { toast((e as Error).message, "error"); }
  };

  const all = res.data ?? [];
  const needs = all.filter((x) => x.open_alerts > 0);
  const rows = filter === "review" ? needs : all;

  return (
    <div className="screen">
      <PageTitle title="Decision log" description="Record research choices with rationale and evidence so they can be revisited when new work arrives."
        actions={<Button variant="primary" icon="plus" onClick={() => { setD(EMPTY); create.clearError(); setOpen(true); }}>Record decision</Button>} />
      <div className="decision-filter">
        <div className="segmented" role="group" aria-label="Filter decisions">
          <button type="button" className={filter === "all" ? "active" : ""} aria-pressed={filter === "all"} onClick={() => setFilter("all")}>All decisions</button>
          <button type="button" className={filter === "review" ? "active" : ""} aria-pressed={filter === "review"} onClick={() => setFilter("review")}>Needs review <span>{needs.length}</span></button>
        </div>
      </div>
      <Boundary res={res} empty={() => rows.length === 0 ? (
        <EmptyState icon="clock" title={filter === "review" ? "Nothing needs review" : "No decisions recorded yet"}
          text="Record a choice such as a method, dataset or metric with your reasons and a quote from a paper. When you add a paper whose reported values conflict, you will be alerted here."
          action={<Button variant="primary" onClick={() => setOpen(true)}>Record decision</Button>} />
      ) : null}>
        {() => (
          <>
            {rows.map((x) => (
              <article className={`decision-card ${x.open_alerts ? "decision-card--alert" : ""}`} key={x.id}>
                <div className="decision-timeline"><i /><span>{dateTime(x.created_at)}</span></div>
                <div className="decision-main">
                  <div className="decision-head">
                    <div>
                      <Pill tone={x.open_alerts ? "amber" : "teal"}>{x.open_alerts ? "Conflict to review" : "Active"}</Pill>
                      <h2>{x.title}</h2>
                      {(x.method || x.dataset || x.metric) && <p className="muted">{[x.method, x.dataset, x.metric].filter(Boolean).join(" · ")}</p>}
                    </div>
                    <IconButton icon="trash" label={`Delete decision: ${x.title}`} onClick={() => void remove(x.id)} />
                  </div>
                  {x.rationale && <p><b>Rationale </b>{x.rationale}</p>}
                  {x.evidence.length > 0 && <div className="decision-evidence">{x.evidence.map((e, i) => (
                    <EvidenceCard key={i} compact c={{ paper_id: e.paper_id, paper_title: e.paper_title, authors: "", year: null, page: e.page ?? 1, quote: e.quote, label: e.label }} />))}</div>}
                  {x.alerts.filter((a) => !a.resolved).map((a) => <AlertBlock key={a.id} a={a} onResolve={() => void resolve(a.id)} />)}
                </div>
              </article>
            ))}
          </>
        )}
      </Boundary>

      {open && (
        <Modal title="Record a decision" onClose={() => setOpen(false)}
          actions={<><Button onClick={() => setOpen(false)}>Cancel</Button>
            <Button variant="primary" disabled={!d.title.trim() || create.busy} onClick={() => void create.run()}>Save decision</Button></>}>
          <div className="stack-form">
            <label className="field"><span>Decision</span><input autoFocus value={d.title} maxLength={300} placeholder="e.g. Use top-10 passages for the baseline" onChange={(e) => setD({ ...d, title: e.target.value })} /></label>
            <label className="field"><span>Why</span><textarea value={d.rationale} maxLength={4000} onChange={(e) => setD({ ...d, rationale: e.target.value })} /></label>
            <label className="field"><span>Method</span><input value={d.method} onChange={(e) => setD({ ...d, method: e.target.value })} /></label>
            <label className="field"><span>Dataset</span><input value={d.dataset} onChange={(e) => setD({ ...d, dataset: e.target.value })} /></label>
            <label className="field"><span>Metric</span><input value={d.metric} onChange={(e) => setD({ ...d, metric: e.target.value })} /></label>
            <label className="field"><span>Linked evidence (optional)</span>
              <select value={d.paper} onChange={(e) => setD({ ...d, paper: e.target.value })}>
                <option value="">No evidence</option>
                {ready.map((p) => <option key={p.id} value={p.id}>{labelOf(p)} · {p.title.slice(0, 50)}</option>)}
              </select></label>
            {d.paper && <>
              <label className="field"><span>Page</span><input type="number" min={1} value={d.page} onChange={(e) => setD({ ...d, page: e.target.value })} /></label>
              <label className="field"><span>Exact quote from that page</span><textarea value={d.quote} maxLength={1500} placeholder="Copy the sentence exactly as it appears in the paper" onChange={(e) => setD({ ...d, quote: e.target.value })} /></label>
              <p className="muted">The quote is checked against the stored paper text. If it is not found, the decision is not saved.</p>
            </>}
            {create.error && <p className="form-error" role="alert">{create.error}</p>}
          </div>
        </Modal>
      )}
    </div>
  );
}
