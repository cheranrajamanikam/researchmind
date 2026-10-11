import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/api/client";
import { useAction } from "@/api/hooks";
import type { PriorWorkResponse } from "@/api/types";
import { AnalysisTitle, HowComputed } from "@/components/Analysis";
import { Icon } from "@/components/Icon";
import { SearchReceiptBlock } from "@/components/SearchReceipt";
import { OllamaBanner, SkeletonCards } from "@/components/states";
import { Banner, Button, Pill } from "@/components/ui";
import { useApp, useProjectId } from "@/context/AppContext";
import { paperLabel, viewerLink } from "@/lib/format";

export default function PriorWork() {
  const pid = useProjectId();
  const { settings, toast } = useApp();
  const [idea, setIdea] = useState("");
  const [out, setOut] = useState<PriorWorkResponse | null>(null);
  const [saved, setSaved] = useState<Set<string>>(new Set());

  const run = useAction(async () => setOut(await api.post<PriorWorkResponse>(`/projects/${pid}/prior-work`, { idea: idea.trim() })));
  const save = useAction(async (c: PriorWorkResponse["closest"][number]) => {
    await api.post(`/projects/${pid}/reading`, { title: c.title, authors: c.authors, year: c.year, venue: c.venue, url: c.url, why: c.why, tags: c.tags, paper_id: c.paper_id });
    setSaved((s) => new Set(s).add(c.title));
    toast("Saved to your reading list");
  });

  return (
    <div className="screen">
      <AnalysisTitle title="Prior-work audit" description="Map a rough idea against possibly related work before deciding how to position it."
        actions={<Link className="button button--secondary" to="/references">Find more references</Link>} />
      <div className="legal-notice" role="note">
        <Icon name="help" />
        <div><b>Not a legal or patentability opinion. No novelty score.</b>
          <p>This is a literature-search aid. Absence of results is not evidence of novelty. Coverage depends on the sources and queries shown in the receipt.</p></div>
      </div>
      <OllamaBanner />
      {!settings?.online_discovery && (
        <Banner tone="info" title="Searching your local library only">Turn on Online discovery in <Link to="/settings">Settings</Link> to also search public scholarly sources with short queries.</Banner>
      )}
      <section className="claim-builder">
        <label>Your rough idea
          <textarea value={idea} onChange={(e) => setIdea(e.target.value)}
            placeholder="Describe the idea in a few sentences: the problem, the method you have in mind, and the data you would use." />
        </label>
        <div className="builder-foot">
          <span>{out ? `Last audited ${new Date(out.receipt.created_at).toLocaleString()}` : "Nothing is sent anywhere unless Online discovery is on, and then only short queries."}</span>
          <Button variant="primary" onClick={() => void run.run()} disabled={run.busy || idea.trim().length < 5}>{run.busy ? "Auditing…" : out ? "Run audit again" : "Run audit"}</Button>
        </div>
      </section>
      {run.error && <p className="form-error" role="alert">{run.error}</p>}
      {run.busy && <SkeletonCards n={3} />}
      {out && !run.busy && (
        <>
          <h2 className="section-title">Closest papers found</h2>
          {out.closest.length === 0 && <p className="muted">Nothing close was found in the sources searched. That is not evidence the idea is new.</p>}
          {out.closest.map((p, i) => (
            <article className="overlap-card" key={`${p.title}-${i}`}>
              <span className="candidate-card__rank">{String(i + 1).padStart(2, "0")}</span>
              <div>
                <h3>{p.title}</h3>
                <p>{paperLabel(p.authors, p.year)} · {p.venue || p.source}</p>
                <div className="overlap-grid">
                  <span><small>SHARED TERMS</small>{p.overlap.shared_terms.length ? p.overlap.shared_terms.join(", ") : "None found"}</span>
                  <span><small>METHOD STATEMENT</small>{p.overlap.method_statement || "Not stated in the available text"}</span>
                  <span><small>DATASETS MENTIONED</small>{p.overlap.datasets.length ? p.overlap.datasets.join(", ") : "None found"}</span>
                </div>
                {p.why && <div className="why"><span>Closest passage</span><blockquote>“{p.why}”</blockquote></div>}
                <div className="chip-row">{p.tags.map((t) => <Pill key={t}>{t}</Pill>)}</div>
              </div>
              <div className="candidate-card__actions">
                <Button icon={saved.has(p.title) ? "check" : "plus"} disabled={saved.has(p.title) || save.busy} onClick={() => void save.run(p)}>{saved.has(p.title) ? "Saved" : "Save to reading list"}</Button>
                {p.paper_id ? <Link className="button button--secondary" to={viewerLink(p.paper_id, p.page ?? 1, p.why)}>Open in viewer</Link>
                  : p.url ? <a className="button button--secondary" href={p.url} target="_blank" rel="noreferrer">Open source</a> : null}
              </div>
            </article>
          ))}
          <SearchReceiptBlock receipt={out.receipt} expanded />
          <HowComputed completedAt={out.receipt.created_at} rows={[
            { label: "Overlap", value: "Shared content words, the first sentence stating a method, and dataset names found in the title and abstract. Plain text matching, not a judgement." },
            { label: "Boundary", value: out.notices.join(" ") },
          ]} />
        </>
      )}
    </div>
  );
}
