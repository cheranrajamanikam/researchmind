import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/api/client";
import { useApi } from "@/api/hooks";
import type { Conflict, ContradictionsResponse } from "@/api/types";
import { AnalysisTitle, Disclaimer, HowComputed } from "@/components/Analysis";
import { Icon } from "@/components/Icon";
import { Boundary } from "@/components/states";
import { EmptyState, Pill } from "@/components/ui";
import { useApp, useProjectId } from "@/context/AppContext";
import { viewerLink } from "@/lib/format";

function Side({ s }: { s: Conflict["a"] }) {
  return (
    <div>
      <span>{s.label}</span>
      <strong>{s.display}</strong>
      <blockquote>“{s.quote}”</blockquote>
      <Link className="link-button" to={viewerLink(s.paper_id, s.page, s.quote)}>p. {s.page} · Open evidence <Icon name="arrow" size={13} /></Link>
    </div>
  );
}

export default function Contradictions() {
  const pid = useProjectId();
  const { settings } = useApp();
  const [tol, setTol] = useState<number | null>(null);
  const [applied, setApplied] = useState<number | null>(null);
  useEffect(() => { if (tol === null && settings) setTol(Math.max(1, settings.tolerance || 5)); }, [settings, tol]);
  // Debounce the slider so the server is not asked on every pixel of movement.
  useEffect(() => {
    if (tol === null) return;
    const t = window.setTimeout(() => setApplied(tol), 250);
    return () => window.clearTimeout(t);
  }, [tol]);

  const res = useApi((s) => api.get<ContradictionsResponse>(`/projects/${pid}/contradictions?tolerance=${applied}`, s), [pid, applied], pid > 0 && applied !== null);

  return (
    <div className="screen screen--wide">
      <AnalysisTitle title="Contradiction view"
        description="Candidate result conflicts where method, dataset, and metric align but reported values differ."
        actions={<Link className="button button--secondary" to="/diff">Open paper diff</Link>} />
      <section className="tolerance-bar">
        <div><b>Numeric matching tolerance</b><span>Flag values differing by more than the selected relative amount.</span></div>
        <input type="range" min={1} max={20} value={tol ?? 5} aria-label="Numeric matching tolerance in percent" onChange={(e) => setTol(Number(e.target.value))} />
        <strong>{tol ?? 5}%</strong>
        <Pill tone="amber">{res.data ? `${res.data.items.length} candidate ${res.data.items.length === 1 ? "conflict" : "conflicts"}` : "Checking…"}</Pill>
      </section>
      <Boundary res={res} empty={(d) => d.items.length === 0 ? (
        <EmptyState icon="check" title="No candidate conflicts at this tolerance"
          text="No two papers report the same method, dataset and metric with values that differ by more than the tolerance. This depends on what was extracted, so check the Extraction review for fields still marked “Verify manually”."
          action={<Link className="button button--primary" to="/extraction">Open extraction review</Link>} />
      ) : null}>
        {(d) => (
          <>
            <p className="muted">{d.note}</p>
            {d.items.map((c) => (
              <article className="contradiction-card" key={c.n}>
                <div className="contradiction-head">
                  <div>
                    <Pill tone="amber">Candidate conflict {String(c.n).padStart(2, "0")}</Pill>
                    <h2>{c.title}</h2>
                    <p>Same stated method, dataset and metric · values differ by {c.relative_difference_pct.toFixed(1)}%</p>
                  </div>
                  <Disclaimer />
                </div>
                <div className="value-compare"><Side s={c.a} /><div className="versus">vs</div><Side s={c.b} /></div>
                {c.setup_differences.length > 0 && (
                  <div className="setup-differences">
                    <b>Reported setup differences</b>
                    {c.setup_differences.map((s) => <div key={s.field}><span>{s.field}</span><b>{s.a || "Not reported"}</b><b>{s.b || "Not reported"}</b></div>)}
                  </div>
                )}
                <div className="reason-grid">
                  <div><span>Possible reasons (not conclusions)</span><ul>{c.possible_reasons.map((r) => <li key={r}>{r}</li>)}</ul></div>
                  <div><span>Candidate experiment (suggestion)</span><p>{c.candidate_experiment}</p>
                    <Link className="button button--secondary" to={`/diff?papers=${c.a.paper_id},${c.b.paper_id}`}>Compare these two setups</Link></div>
                </div>
              </article>
            ))}
            <HowComputed rows={[
              { label: "Matching", value: "Pairs are compared only when the extracted method, dataset and metric are the same after normalisation." },
              { label: "Difference", value: `Relative difference between the two values, flagged above ${d.tolerance}%.` },
              { label: "Reasons", value: "Listed from the setup differences found. They are possibilities, never conclusions." },
            ]} />
          </>
        )}
      </Boundary>
    </div>
  );
}
