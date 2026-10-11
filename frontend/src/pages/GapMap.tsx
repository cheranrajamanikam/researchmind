import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/api/client";
import { useApi } from "@/api/hooks";
import type { GapResponse } from "@/api/types";
import { AnalysisTitle, HowComputed } from "@/components/Analysis";
import { Icon } from "@/components/Icon";
import { Boundary, NoPapers, OllamaBanner } from "@/components/states";
import { Button, EmptyState, Pill } from "@/components/ui";
import { useProjectId } from "@/context/AppContext";
import { viewerLink } from "@/lib/format";

export default function GapMap() {
  const pid = useProjectId();
  const [adjust, setAdjust] = useState(false);
  const [thr, setThr] = useState<number | null>(null);
  const [applied, setApplied] = useState<number | null>(null);
  const [open, setOpen] = useState<Set<number>>(new Set());
  const res = useApi((s) => api.get<GapResponse>(`/projects/${pid}/gaps${applied ? `?threshold=${applied}` : ""}`, s), [pid, applied], pid > 0);

  return (
    <div className="screen">
      <AnalysisTitle title="Candidate gap map"
        description="Clusters of limitations and future-work statements for you to inspect, not claims of novelty."
        actions={<Button onClick={() => { setAdjust(!adjust); if (thr === null && res.data?.threshold) setThr(res.data.threshold); }}>Adjust clustering</Button>} />
      <OllamaBanner />
      <div className="gap-notice"><Pill tone="blue">Candidate gaps for you to evaluate</Pill>
        <p>Clusters reflect language in your library. A dense cluster may indicate active work rather than an open gap.</p></div>
      {adjust && (
        <section className="tolerance-bar">
          <div><b>Cluster tightness</b><span>Higher groups only very similar statements; lower merges related ones.</span></div>
          <input type="range" min={0.1} max={0.9} step={0.05} value={thr ?? res.data?.threshold ?? 0.6} aria-label="Cluster similarity threshold"
            onChange={(e) => setThr(Number(e.target.value))} onPointerUp={() => setApplied(thr)} onKeyUp={() => setApplied(thr)} />
          <strong>{(thr ?? res.data?.threshold ?? 0.6).toFixed(2)}</strong>
        </section>
      )}
      <Boundary res={res} empty={(d) => d.clusters.length === 0 ? (
        d.statements_total === 0 && !res.loading
          ? <EmptyState icon="grid" title="No limitation or future-work statements found"
              text="The gap map groups sentences where papers describe their own limitations or future work. Add more papers with those sections, or check that papers finished processing."
              action={<Link className="button button--primary" to="/upload">Add papers</Link>} />
          : <NoPapers what="the gap map" />
      ) : null}>
        {(d) => (
          <>
            <div className="gap-grid">
              {d.clusters.map((c) => {
                const shown = open.has(c.n) ? c.statements : c.statements.slice(0, 2);
                return (
                  <article className="gap-card" key={c.n}>
                    <div className={`gap-orb orb-${(c.n - 1) % 3}`}><span>{c.paper_count}</span><small>{c.paper_count === 1 ? "paper" : "papers"}</small></div>
                    <div>
                      <span>CLUSTER {String(c.n).padStart(2, "0")}</span>
                      <h2>{c.label}</h2>
                      <p>{c.statement_count} supporting statements across {c.paper_count} {c.paper_count === 1 ? "paper" : "papers"}</p>
                      <div className="chip-row">{c.kinds.map((k) => <Pill key={k}>{k}</Pill>)}</div>
                    </div>
                    <div className="gap-evidence">
                      <b>Supporting statements</b>
                      {shown.map((s, i) => (
                        <div key={i}>
                          <blockquote>“{s.quote}”</blockquote>
                          <span>{s.label} · p. {s.page}</span>{" "}
                          <Link className="link-button" to={viewerLink(s.paper_id, s.page, s.quote)}>Open <Icon name="arrow" size={12} /></Link>
                        </div>
                      ))}
                      {c.statements.length > 2 && (
                        <Button variant="ghost" onClick={() => setOpen((o) => { const n = new Set(o); if (n.has(c.n)) n.delete(c.n); else n.add(c.n); return n; })}>
                          {open.has(c.n) ? "Show fewer" : `Review all ${c.statement_count} statements`}
                        </Button>
                      )}
                    </div>
                  </article>
                );
              })}
            </div>
            <HowComputed rows={[
              { label: "Collected", value: `${d.statements_total} sentences of six words or more containing cue phrases such as “limitation”, “future work” or “remains underexplored”.` },
              { label: "Grouping", value: d.method === "embeddings" ? "Embedding similarity from your local model." : "Word-overlap term vectors, because embeddings were unavailable (Ollama offline)." },
              { label: "Labels", value: "Cluster names come from the most frequent terms, not from a generated claim." },
              ...(d.note ? [{ label: "Note", value: d.note }] : []),
            ]} />
          </>
        )}
      </Boundary>
    </div>
  );
}
