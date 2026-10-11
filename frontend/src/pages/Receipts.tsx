import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "@/api/client";
import { useApi } from "@/api/hooks";
import type { Candidate, Receipt } from "@/api/types";
import { HowComputed } from "@/components/Analysis";
import { downloadText } from "@/components/PaperPicker";
import { SearchReceiptBlock } from "@/components/SearchReceipt";
import { Boundary } from "@/components/states";
import { Button, EmptyState, PageTitle, Pill } from "@/components/ui";
import { useProjectId } from "@/context/AppContext";
import { dateTime } from "@/lib/format";
import { CandidateCard } from "./FindReferences";

export function Receipts() {
  const pid = useProjectId();
  const nav = useNavigate();
  const res = useApi((s) => api.get<Receipt[]>(`/projects/${pid}/receipts`, s), [pid], pid > 0);
  return (
    <div className="screen screen--narrow">
      <PageTitle eyebrow="Reference discovery" title="Search receipts"
        description="Every discovery run leaves a record of what was searched, where, when, and what was not covered." />
      <Boundary res={res} empty={(d) => d.length === 0 ? (
        <EmptyState icon="file" title="No receipts yet" text="Run Find references or a Prior-work audit and the receipt is saved here."
          action={<Link className="button button--primary" to="/references">Find references</Link>} />
      ) : null}>
        {(rows) => (
          <section className="panel">
            {rows.map((r) => (
              <div className="project-row" key={r.id}>
                <div>
                  <b>{r.kind === "prior_work" ? "Prior-work audit" : "Find references"}</b>
                  <p className="muted">{r.input_text.length > 120 ? `${r.input_text.slice(0, 120)}…` : r.input_text}</p>
                  <span className="muted">{dateTime(r.created_at)} · {r.queries.length} queries · {r.result_count ?? 0} candidates</span>
                </div>
                <Pill tone={r.online ? "blue" : "neutral"}>{r.online ? "Online discovery" : "Local only"}</Pill>
                <Button onClick={() => nav(`/receipts/${r.id}`)}>Open</Button>
              </div>
            ))}
          </section>
        )}
      </Boundary>
    </div>
  );
}

export function ReceiptDetail() {
  const { id } = useParams();
  const rid = Number(id);
  const res = useApi((s) => api.get<Receipt>(`/receipts/${rid}`, s), [rid], Number.isFinite(rid));
  return (
    <div className="screen screen--narrow">
      <Boundary res={res}>
        {(r) => {
          const c = r.counts;
          const funnel: [string, unknown][] = [
            ["Results returned", c.results_returned], ["Duplicates removed", c.duplicates_removed], ["Titles screened", c.titles_screened],
            ["Abstracts inspected", c.abstracts_inspected], ["Candidates kept", c.candidates],
          ];
          return (
            <>
              <PageTitle eyebrow="Reference discovery" title="Search receipt"
                description="A reproducible record of what was searched, where, when, and what was not covered."
                actions={<Button icon="download" onClick={() => downloadText(`search-receipt-${r.id}.json`, JSON.stringify(r, null, 2), "application/json")}>Export receipt</Button>} />
              <SearchReceiptBlock receipt={r} expanded />
              <section className="panel receipt-results">
                <div className="section-head"><div><h2>Result funnel</h2><p>Counts at each screening stage</p></div></div>
                {funnel.map(([k, v]) => <div key={k}><span>{k}</span><b>{String(v ?? 0)}</b></div>)}
              </section>
              <h2 className="section-title">Candidates from this run</h2>
              {(r.results as Candidate[]).map((cand) => <CandidateCard key={`${cand.title}-${cand.rank}`} c={cand} saved={false} onSave={() => undefined} readOnly />)}
              <HowComputed completedAt={r.created_at} rows={[{ label: "Input", value: r.input_text }]} />
            </>
          );
        }}
      </Boundary>
    </div>
  );
}
