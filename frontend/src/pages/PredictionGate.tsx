import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "@/api/client";
import { useAction, useApi } from "@/api/hooks";
import type { PredictionItem, PredictionResult } from "@/api/types";
import { HowComputed } from "@/components/Analysis";
import { Disclaimer } from "@/components/Analysis";
import { EvidenceCard, evidenceFrom } from "@/components/Evidence";
import { PaperChecklist, useProjectPapers } from "@/components/PaperPicker";
import { NoPapers, SkeletonCards } from "@/components/states";
import { Button, PageTitle, Pill, Switch } from "@/components/ui";
import { useApp, useProjectId } from "@/context/AppContext";
import { relativeTime } from "@/lib/format";

interface Past { id: number; created_at: string; prediction: string; counts: Record<string, number> }

function Bucket({ title, tone, items, empty }: { title: string; tone: "teal" | "amber" | "blue"; items: PredictionItem[]; empty: string }) {
  return (
    <article>
      <Pill tone={tone}>{title}</Pill>
      {items.length === 0 && <p className="muted">{empty}</p>}
      {items.map((it, i) => (
        <div key={i}>
          <h3>{it.statement}</h3>
          {it.your_sentence && <p className="muted">You wrote: “{it.your_sentence}”</p>}
          {it.evidence.slice(0, 3).map((e, j) => <EvidenceCard key={j} compact c={evidenceFrom(e)} />)}
        </div>
      ))}
    </article>
  );
}

export default function PredictionGate() {
  const pid = useProjectId();
  const { project, refreshProjects, toast } = useApp();
  const { res, ready } = useProjectPapers();
  const [sp] = useSearchParams();
  const [selected, setSelected] = useState<number[]>(() => (sp.get("papers") ?? "").split(",").map(Number).filter(Boolean));
  const [text, setText] = useState("");
  const [result, setResult] = useState<PredictionResult | null>(null);
  const [reflection, setReflection] = useState("");
  const past = useApi((s) => api.get<Past[]>(`/projects/${pid}/predictions`, s), [pid], pid > 0);

  const submit = useAction(async () => {
    const r = await api.post<PredictionResult>(`/projects/${pid}/predictions`, { paper_ids: selected, prediction: text.trim() });
    setResult(r);
    setReflection("");
    past.reload();
  });
  const saveReflection = useAction(async () => {
    if (!result) return;
    await api.patch(`/predictions/${result.id}`, { reflection });
    toast("Reflection saved");
  });
  const openPast = useAction(async (id: number) => {
    const r = await api.get<PredictionResult>(`/predictions/${id}`);
    setResult(r);
    setReflection(r.reflection ?? "");
  });
  const setThinkFirst = async (v: boolean) => {
    try { await api.patch(`/projects/${pid}`, { think_first: v }); await refreshProjects(); }
    catch (e) { toast((e as Error).message, "error"); }
  };

  if (result) {
    return (
      <div className="screen screen--narrow">
        <PageTitle eyebrow="Think first · comparison revealed" title="Compare your prediction with the evidence"
          description="These prompts organize your review; they do not grade your prediction."
          actions={<><Link className="button button--secondary" to={`/diff?papers=${result.papers.map((p) => p.id).join(",")}`}>Open full paper diff</Link>
            <Button onClick={() => setResult(null)}>New prediction</Button></>} />
        <div className="prediction-stepper done"><span>1 <b>Predicted</b></span><i /><span>2 <b>Compare</b></span><i /><span className="active">3 <b>Reflect</b></span></div>
        <div className="analysis-meta"><Disclaimer /><span>{result.papers.map((p) => p.label).join(" · ")}</span></div>
        <section className="prediction-card"><label>Your prediction<textarea readOnly value={result.prediction} /></label></section>
        <div className="prediction-results">
          <Bucket title="Matched" tone="teal" items={result.matched} empty="Nothing in your note lined up with a reported value." />
          <Bucket title="Possibly missed" tone="amber" items={result.possibly_missed} empty="No notable setup difference went unmentioned." />
          <Bucket title="Check this reading" tone="blue" items={result.check_reading} empty="Nothing in your note conflicts with the extracted fields." />
        </div>
        <p className="muted">{result.note}</p>
        <div className="reflection-box">
          <label>What changed in your thinking?
            <textarea value={reflection} maxLength={4000} placeholder="Write one or two sentences in your own words…" onChange={(e) => setReflection(e.target.value)} /></label>
          <Button variant="primary" onClick={() => void saveReflection.run()} disabled={saveReflection.busy || !reflection.trim()}>Save reflection</Button>
        </div>
        <HowComputed rows={[
          { label: "Method", value: "Your note is compared with confirmed and extracted fields using plain matching on numbers and names. There is no language model grading." },
          { label: "Buckets", value: "Matched, possibly missed and check this reading are prompts for you, not marks." },
        ]} />
      </div>
    );
  }

  return (
    <div className="screen screen--narrow">
      <PageTitle eyebrow="Think first" title="What do you expect to find?"
        description="Write your prediction before revealing the extracted comparison. Your note stays linked to this analysis." />
      <div className="prediction-stepper"><span className="active">1 <b>Predict</b></span><i /><span>2 <b>Compare</b></span><i /><span>3 <b>Reflect</b></span></div>
      {res.data === undefined ? <SkeletonCards n={2} /> : ready.length === 0 ? <NoPapers what="the prediction gate" /> : (
        <section className="prediction-card">
          <div className="compare-context"><div><Pill>{selected.length} {selected.length === 1 ? "paper" : "papers"}</Pill>
            <h2>Choose the papers to compare</h2><p>The comparison stays hidden until you submit.</p></div></div>
          <PaperChecklist papers={ready} selected={selected} onChange={setSelected} />
          <label>Your prediction or summary
            <textarea value={text} minLength={10} onChange={(e) => setText(e.target.value)} placeholder="Before seeing the extracted fields, I expect…" />
          </label>
          <div className="prediction-prompts"><b>Optional prompts</b><span>Which result do you expect to be strongest?</span><span>What setup difference may matter most?</span></div>
          {submit.error && <p className="form-error" role="alert">{submit.error}</p>}
          <div className="builder-foot">
            <label><Switch checked={project?.think_first ?? false} onChange={(v) => void setThinkFirst(v)} label="Use Think-first by default for this project" /> Use Think-first by default for this project</label>
            <Button variant="primary" onClick={() => void submit.run()} disabled={submit.busy || selected.length < 1 || text.trim().length < 10}>
              {submit.busy ? "Comparing…" : "Save prediction and reveal comparison"}
            </Button>
          </div>
        </section>
      )}
      {past.data && past.data.length > 0 && (
        <section className="panel">
          <div className="section-head"><div><h2>Earlier predictions</h2><p>Open one to see the comparison again</p></div></div>
          {past.data.map((p) => (
            <div className="project-row" key={p.id}>
              <div><b>{p.prediction.length > 110 ? `${p.prediction.slice(0, 110)}…` : p.prediction}</b>
                <span className="muted">{relativeTime(p.created_at)} · {p.counts.matched} matched · {p.counts.possibly_missed} possibly missed · {p.counts.check_reading} to check</span></div>
              <Button onClick={() => void openPast.run(p.id)}>Open</Button>
            </div>
          ))}
        </section>
      )}
    </div>
  );
}
