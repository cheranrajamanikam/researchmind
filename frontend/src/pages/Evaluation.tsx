import { useState } from "react";
import { api } from "@/api/client";
import { useAction, useApi } from "@/api/hooks";
import type { EvalRun } from "@/api/types";
import { AnalysisTitle, HowComputed } from "@/components/Analysis";
import { LineChart, Ring } from "@/components/Charts";
import { Icon } from "@/components/Icon";
import { Boundary, OllamaBanner } from "@/components/states";
import { Banner, Button, EmptyState, Pill } from "@/components/ui";
import { useApp, useProjectId } from "@/context/AppContext";
import { delta, num, pct } from "@/lib/format";

export default function Evaluation() {
  const pid = useProjectId();
  const { toast, ollama } = useApp();
  const runs = useApi((s) => api.get<EvalRun[]>(`/projects/${pid}/eval/runs`, s), [pid], pid > 0);
  const questions = useApi((s) => api.get<{ count: number }>(`/projects/${pid}/eval/questions`, s), [pid], pid > 0);
  const [sel, setSel] = useState<number | null>(null);
  const latest = runs.data?.[0];
  const runId = sel ?? latest?.id ?? null;
  const detail = useApi((s) => api.get<EvalRun>(`/eval/runs/${runId}`, s), [runId], runId !== null);

  const load = useAction(async () => {
    const r = await api.post<{ questions: number }>(`/projects/${pid}/eval/samples`);
    questions.reload();
    toast(`Loaded ${r.questions} sample questions`);
  });
  const run = useAction(async () => {
    const r = await api.post<EvalRun>(`/projects/${pid}/eval/run`, { k: 10, use_judge: false });
    setSel(r.id);
    runs.reload();
    toast("Evaluation finished");
  });

  const hasQuestions = (questions.data?.count ?? 0) > 0;
  const current = detail.data ?? latest;
  const prior = runs.data && runs.data.length > 1 ? runs.data[1] : undefined;
  const m = current?.metrics;
  const history = [...(runs.data ?? [])].reverse();

  const cards: { label: string; value: string; d: string | null; review?: boolean }[] = m ? [
    { label: `Recall@${m.k}`, value: num(m.recall_at_k), d: delta(m.recall_at_k, prior?.metrics.recall_at_k) },
    { label: "MRR", value: num(m.mrr), d: delta(m.mrr, prior?.metrics.mrr) },
    { label: "Citation faithfulness", value: pct(m.citation_faithfulness), d: delta(m.citation_faithfulness, prior?.metrics.citation_faithfulness, true) },
    { label: "Refusal accuracy", value: pct(m.refusal_accuracy), d: delta(m.refusal_accuracy, prior?.metrics.refusal_accuracy, true), review: (m.refusal_accuracy ?? 1) < 0.8 },
  ] : [];

  return (
    <div className="screen">
      <AnalysisTitle title="Evaluation"
        description="Track retrieval quality, citation grounding, and appropriate refusal across your test set."
        meta={current ? `Run #${current.id} · ${new Date(current.created_at).toLocaleString()} · ${current.metrics.answer_mode}` : "No runs yet"}
        actions={<>
          {!hasQuestions && <Button onClick={() => void load.run()} disabled={load.busy}>Load sample questions</Button>}
          {current && <Button icon="download" onClick={() => void api.download(`/eval/runs/${current.id}/report.md`, `researchmind-eval-${current.id}.md`)}>Export report</Button>}
          <Button variant="primary" onClick={() => void run.run()} disabled={run.busy || !hasQuestions}>{run.busy ? "Running…" : "Run evaluation"}</Button>
        </>} />
      <OllamaBanner />
      {(load.error || run.error) && <p className="form-error" role="alert">{load.error || run.error}</p>}
      {ollama?.reachable === false && <Banner tone="info" title="Offline evaluation">Without Ollama the run uses extractive answers and keyword retrieval. Results are labelled with the mode used.</Banner>}

      <Boundary res={runs} empty={(d) => d.length === 0 ? (
        <EmptyState icon="grid" title="No evaluation runs yet"
          text={hasQuestions
            ? `${questions.data?.count} questions are ready. Run the evaluation to measure retrieval, citation faithfulness and refusal on your own papers.`
            : "An evaluation needs a gold set of questions about your papers, including some the papers cannot answer. Load the bundled sample suite (after uploading the sample papers) or add your own."}
          action={hasQuestions ? <Button variant="primary" onClick={() => void run.run()} disabled={run.busy}>Run evaluation</Button>
            : <Button onClick={() => void load.run()} disabled={load.busy}>Load sample questions</Button>} />
      ) : null}>
        {() => m && (
          <>
            <div className="eval-metrics">
              {cards.map((c) => (
                <div className="metric" key={c.label}>
                  <span>{c.label}</span><strong>{c.value}</strong>
                  <small className={c.review ? "review-text" : ""}>{c.d ? `${c.d} vs prior run` : "first run"}</small>
                </div>
              ))}
            </div>
            <div className="analysis-grid">
              <section className="panel analysis-chart">
                <div className="section-head"><div><h2>Performance history</h2><p>{history.length} {history.length === 1 ? "run" : "runs"} · {m.answerable + m.unanswerable} questions each</p></div></div>
                <LineChart ariaLabel="Citation faithfulness and recall across evaluation runs" labels={history.map((r) => `#${r.id}`)}
                  series={[
                    { name: "Citation faithfulness", tone: "teal", values: history.map((r) => r.metrics.citation_faithfulness) },
                    { name: `Recall@${m.k}`, tone: "blue", values: history.map((r) => r.metrics.recall_at_k) },
                  ]} />
              </section>
              <section className="panel">
                <div className="section-head"><div><h2>Extraction accuracy</h2>
                  <p>{m.extraction ? `Hand-labelled set · ${m.extraction.n_fields} fields, ${m.extraction.n_papers} papers` : "Not measured in this run"}</p></div></div>
                <Ring value={m.extraction?.overall ?? null} caption="exact match" />
                {m.extraction && Object.entries(m.extraction.by_field).map(([k, v]) => (
                  <div className="accuracy-row" key={k}><span>{k}</span><div className="progress"><i style={{ width: `${v * 100}%` }} /></div><b>{Math.round(v * 100)}%</b></div>
                ))}
              </section>
            </div>
            <section className="table-panel">
              <div className="section-head"><div><h2>Per-question results</h2>
                <p>{detail.data?.details?.length ?? 0} questions · {m.answerable} answerable, {m.unanswerable} unanswerable</p></div>
                {runs.data && runs.data.length > 1 && (
                  <label className="field"><span className="sr-only">Run</span>
                    <select value={runId ?? ""} onChange={(e) => setSel(Number(e.target.value))} aria-label="Choose a run">
                      {runs.data.map((r) => <option key={r.id} value={r.id}>Run #{r.id} · {new Date(r.created_at).toLocaleDateString()}</option>)}
                    </select></label>
                )}
              </div>
              <div className="data-scroll">
                <table className="data-table">
                  <thead><tr><th>Question</th><th>Behavior</th><th>Citations valid</th><th>Faithfulness</th><th>Status</th></tr></thead>
                  <tbody>
                    {(detail.data?.details ?? []).map((d) => (
                      <tr key={d.question}>
                        <td><b>{d.question}</b>{!d.answerable && <div className="muted">Expected: refusal</div>}</td>
                        <td>{d.behavior}</td><td>{d.citations_valid}</td>
                        <td>{d.faithfulness === null ? "—" : d.faithfulness.toFixed(2)}</td>
                        <td><Pill tone={d.result === "Review" ? "amber" : "teal"}>{d.result === "Pass" && <Icon name="check" size={11} />}{d.result}</Pill></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <HowComputed completedAt={current?.created_at} rows={[
                { label: "Retrieval", value: `${m.retrieval_mode}, top ${m.k} passages per question` },
                { label: "Faithfulness", value: m.judge.used ? `Quote match plus an LLM judge on ${m.judge.judged} answers` : "Cited quote must appear verbatim in the cited page (no LLM judge)" },
                { label: "Refusal", value: "Unanswerable questions pass only when the system answers “insufficient evidence”" },
              ]} />
            </section>
          </>
        )}
      </Boundary>
    </div>
  );
}
