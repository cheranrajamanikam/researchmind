import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/api/client";
import { useAction, useApi } from "@/api/hooks";
import type { AuditResponse, AuditRow } from "@/api/types";
import { AnalysisTitle, HowComputed } from "@/components/Analysis";
import { Icon } from "@/components/Icon";
import { labelOf, useProjectPapers } from "@/components/PaperPicker";
import { Boundary, OllamaBanner } from "@/components/states";
import { Button, EmptyState, Pill } from "@/components/ui";
import { useProjectId } from "@/context/AppContext";
import { viewerLink } from "@/lib/format";

function AuditCard({ a }: { a: AuditRow }) {
  const review = /review|weak|low/i.test(a.overlap_label);
  return (
    <article className="audit-card">
      <div className="audit-head">
        <span>Citation {a.marker}{a.location ? ` · ${a.location}` : ""}{a.citing_paper ? ` · in ${a.citing_paper.title}` : ""}</span>
      </div>
      <div className="audit-compare">
        <div><small>CITING SENTENCE</small><blockquote>{a.citing_sentence}</blockquote></div>
        <div>
          <small>CITED PAPER · MOST RELEVANT PASSAGE</small>
          <blockquote>“{a.passage.quote}”</blockquote>
          <span>{a.cited.label} · p. {a.passage.page}</span>
        </div>
      </div>
      <div className="audit-foot">
        <Pill tone={review ? "amber" : "blue"}>{a.overlap_label}</Pill>
        <Link className="button button--ghost" to={viewerLink(a.cited.paper_id, a.passage.page, a.passage.quote)}>Open cited passage <Icon name="arrow" size={13} /></Link>
      </div>
    </article>
  );
}

export default function CitationAudit() {
  const pid = useProjectId();
  const { ready } = useProjectPapers();
  const lib = useApi((s) => api.get<AuditResponse>(`/projects/${pid}/citation-audit`, s), [pid], pid > 0);
  const [draft, setDraft] = useState("");
  const [mapping, setMapping] = useState<Record<string, number>>({});
  const [out, setOut] = useState<AuditResponse | null>(null);
  const markers = useMemo(() => [...new Set([...draft.matchAll(/\[(\d{1,3})\]/g)].map((m) => m[1]))], [draft]);

  const run = useAction(async () => {
    const usable = Object.fromEntries(Object.entries(mapping).filter(([k, v]) => markers.includes(k) && v));
    setOut(await api.post<AuditResponse>(`/projects/${pid}/citation-audit`, { text: draft, mapping: usable }));
  });

  return (
    <div className="screen">
      <AnalysisTitle title="Library citation audit"
        description="Compare each citing sentence with the most relevant passage in the cited paper. Evidence side by side, no verdict." />
      <OllamaBanner />

      <section className="claim-builder">
        <label>Check a draft
          <textarea value={draft} onChange={(e) => setDraft(e.target.value)}
            placeholder="Paste a paragraph that cites your library by number, e.g. “Retrieval improves factuality [1].”" />
        </label>
        {markers.length > 0 && (
          <div className="query-strip">
            <div><b>Which paper is each reference?</b><span>Match every number to a paper in your library</span></div>
            {markers.map((m) => (
              <label key={m}>[{m}]
                <select aria-label={`Paper for reference ${m}`} value={mapping[m] ?? ""} onChange={(e) => setMapping({ ...mapping, [m]: Number(e.target.value) })}>
                  <option value="">Choose a paper…</option>
                  {ready.map((p) => <option key={p.id} value={p.id}>{labelOf(p)} · {p.title.slice(0, 50)}</option>)}
                </select>
              </label>
            ))}
          </div>
        )}
        <div className="builder-foot">
          <span>Your draft is analysed on this device and is not stored.</span>
          <Button variant="primary" onClick={() => void run.run()} disabled={run.busy || !draft.trim() || markers.length === 0}>{run.busy ? "Checking…" : "Audit draft citations"}</Button>
        </div>
      </section>
      {run.error && <p className="form-error" role="alert">{run.error}</p>}
      {out && (
        <>
          <h2 className="section-title">Your draft</h2>
          {out.items.length === 0 ? <EmptyState icon="file" title="No matched citations" text="Add [1]-style markers and match each to a paper above." /> : out.items.map((a, i) => <AuditCard key={i} a={a} />)}
        </>
      )}

      <h2 className="section-title">Papers in your library that cite each other</h2>
      <Boundary res={lib} empty={(d) => d.items.length === 0 ? (
        <EmptyState icon="book" title="No in-library citations found"
          text="This lists sentences where one uploaded paper cites another uploaded paper. With few papers there may be none. The draft checker above works regardless." />
      ) : null}>
        {(d) => <>{d.items.map((a, i) => <AuditCard key={i} a={a} />)}
          <HowComputed rows={[
            { label: "Method", value: "Author–year citations such as “Lewis et al., 2020” are located in each paper and matched to another paper in your library by surname and year. The most similar passage in the cited paper is then found by search. Numbered references need the draft checker above." },
            { label: "Output", value: d.note },
          ]} /></>}
      </Boundary>
    </div>
  );
}
