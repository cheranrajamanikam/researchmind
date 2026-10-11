import { Link } from "react-router-dom";
import { api } from "@/api/client";
import { useApi } from "@/api/hooks";
import type { NumericResponse } from "@/api/types";
import { Agreement, AnalysisTitle, HowComputed } from "@/components/Analysis";
import { PaperSelect, usePaperParam, useProjectPapers } from "@/components/PaperPicker";
import { Boundary, NoPapers, SkeletonCards } from "@/components/states";
import { EmptyState, Pill } from "@/components/ui";
import { viewerLink } from "@/lib/format";

export default function NumericConsistency() {
  const { res, ready } = useProjectPapers();
  const [paperId, setPaperId] = usePaperParam(ready);
  const out = useApi((s) => api.get<NumericResponse>(`/papers/${paperId}/numeric`, s), [paperId], paperId !== null);

  return (
    <div className="screen">
      <AnalysisTitle title="Numeric consistency"
        description="Potential mismatches between values reported in the abstract, results, tables and conclusion of one paper." />
      {res.data === undefined ? <SkeletonCards n={2} /> : ready.length === 0 ? <NoPapers what="numeric consistency" /> : (
        <>
          <PaperSelect papers={ready} value={paperId} onChange={setPaperId} />
          <Boundary res={out} skeleton={<SkeletonCards n={2} />} empty={(d) => d.mismatches.length === 0 ? (
            <EmptyState icon="check" title="No numeric mismatches located"
              text={`${d.mentions_checked} numeric mentions were compared across sections. “None located” is not a guarantee. Tables parsed from PDFs can be incomplete, so check anything that matters by eye.`} />
          ) : null}>
            {(d) => (
              <>
                <section className="paper-context">
                  <div><h2>{d.title}</h2><p>{d.mismatches.length} candidate {d.mismatches.length === 1 ? "mismatch" : "mismatches"} · {d.mentions_checked} numeric mentions checked</p></div>
                  <Agreement status="verify" />
                </section>
                {d.mismatches.map((m, i) => (
                  <article className="mismatch-card" key={i}>
                    <div className="mismatch-head">
                      <div><Pill tone="amber">Verify manually</Pill><h2>{m.label}</h2><p>{m.summary}</p></div>
                      <Link className="button button--secondary" to={viewerLink(d.paper_id, m.a.page, m.a.quote)}>Open paper</Link>
                    </div>
                    <div className="quote-compare">
                      {[m.a, m.b].map((s, j) => (
                        <div key={j}>
                          <span>{s.section} · p. {s.page}</span><strong>{s.value}</strong>
                          <blockquote>“{s.quote}”</blockquote>
                          <Link className="link-button" to={viewerLink(d.paper_id, s.page, s.quote)}>Open p. {s.page}</Link>
                        </div>
                      ))}
                    </div>
                  </article>
                ))}
                <HowComputed rows={[
                  { label: "Method", value: "Numbers with a metric or dataset name are collected per section with a regular expression, grouped by what they measure, and compared. No language model is involved." },
                  { label: "Limit", value: d.note },
                ]} />
              </>
            )}
          </Boundary>
        </>
      )}
    </div>
  );
}
