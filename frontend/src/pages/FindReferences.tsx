import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "@/api/client";
import { useAction } from "@/api/hooks";
import type { Candidate, Receipt } from "@/api/types";
import { AnalysisTitle, Disclaimer } from "@/components/Analysis";
import { Icon } from "@/components/Icon";
import { SearchReceiptBlock } from "@/components/SearchReceipt";
import { OllamaBanner, SkeletonCards } from "@/components/states";
import { Banner, Button, EmptyState, IconButton, Pill } from "@/components/ui";
import { useApp, useProjectId } from "@/context/AppContext";
import { paperLabel, viewerLink } from "@/lib/format";

export function CandidateCard({
  c, saved, onSave, busy, readOnly = false,
}: { c: Candidate; saved: boolean; onSave: () => void; busy?: boolean; readOnly?: boolean }) {
  return (
    <article className="candidate-card">
      <div className="candidate-card__rank">{String(c.rank).padStart(2, "0")}</div>
      <div>
        <h2>{c.title}</h2>
        <p>{paperLabel(c.authors, c.year)} · {c.venue || c.source}</p>
        <div className="why">
          <span>Why possibly relevant</span>
          {c.why ? <blockquote>“{c.why}”</blockquote> : <blockquote className="muted">No abstract was available to quote.</blockquote>}
          <small>{c.why_source === "abstract" ? "Abstract · exact sentence" : c.why_source || "Source text"}</small>
        </div>
        <div className="chip-row">{c.tags.map((t) => <Pill key={t}>{t}</Pill>)}<Pill tone="blue">{c.source}</Pill></div>
      </div>
      <div className="candidate-card__actions">
        {!readOnly && (
          <Button variant={saved ? "secondary" : "primary"} icon={saved ? "check" : "plus"} onClick={onSave} disabled={saved || busy}>
            {saved ? "Saved" : "Save to reading list"}
          </Button>
        )}
        {c.paper_id ? <Link className="button button--secondary" to={viewerLink(c.paper_id, c.page ?? 1, c.why)}>Open in viewer</Link>
          : c.url ? <a className="button button--secondary" href={c.url} target="_blank" rel="noreferrer">Open abstract</a> : null}
      </div>
    </article>
  );
}

export default function FindReferences() {
  const pid = useProjectId();
  const nav = useNavigate();
  const { settings, toast } = useApp();
  const [text, setText] = useState("");
  const [queries, setQueries] = useState<string[] | null>(null);
  const [receipt, setReceipt] = useState<Receipt | null>(null);
  const [saved, setSaved] = useState<Set<string>>(new Set());

  const search = useAction(async (useEdited: boolean) => {
    const body: { text: string; queries?: string[] } = { text: text.trim() };
    if (useEdited && queries?.some((q) => q.trim())) body.queries = queries.filter((q) => q.trim());
    const r = await api.post<Receipt>(`/projects/${pid}/discover`, body);
    setReceipt(r);
    setQueries(r.queries);
  });

  const save = useAction(async (c: Candidate) => {
    await api.post(`/projects/${pid}/reading`, {
      title: c.title, authors: c.authors, year: c.year, venue: c.venue, url: c.url, why: c.why, tags: c.tags, paper_id: c.paper_id,
    });
    setSaved((s) => new Set(s).add(c.title));
    toast("Saved to your reading list");
  });

  const online = settings?.online_discovery ?? false;
  const results = (receipt?.results ?? []) as Candidate[];

  return (
    <div className="screen">
      <AnalysisTitle title="Find references"
        description="Turn a claim into editable searches, then inspect why each candidate may be relevant."
        actions={receipt ? <Button onClick={() => nav(`/receipts/${receipt.id}`)}>View search receipt</Button> : <Link className="button button--secondary" to="/receipts">Past receipts</Link>} />
      <OllamaBanner />
      {!online && (
        <Banner tone="info" title="Searching your local library only">
          Online discovery is off, so nothing leaves this device. Turn it on in <Link to="/settings">Settings</Link> to also search OpenAlex, Semantic Scholar and arXiv with short queries.
        </Banner>
      )}
      <section className="claim-builder">
        <label>Claim or paragraph to investigate
          <textarea value={text} onChange={(e) => setText(e.target.value)}
            placeholder="e.g. Increasing retrieval depth improves answer coverage, but may reduce citation faithfulness when irrelevant passages enter the context." />
        </label>
        <div className="builder-foot">
          <span>{online ? "Only the short queries shown below are sent to scholarly sources. Never your paper text." : "Queries are shown before and after every search."}</span>
          <Button variant="primary" icon="search" onClick={() => void search.run(false)} disabled={search.busy || text.trim().length < 3}>
            {search.busy ? "Searching…" : "Find possibly relevant work"}
          </Button>
        </div>
      </section>
      {search.error && <p className="form-error" role="alert">{search.error}</p>}

      {queries && (
        <div className="query-strip">
          <div><b>Generated queries</b><span>Edit these, then search again</span></div>
          {queries.map((q, i) => (
            <label key={i}>
              <input aria-label={`Query ${i + 1}`} value={q} maxLength={200} onChange={(e) => setQueries(queries.map((x, j) => (j === i ? e.target.value : x)))} />
              <IconButton icon="close" label="Remove query" onClick={() => setQueries(queries.filter((_, j) => j !== i))} />
            </label>
          ))}
          {queries.length < 5 && <IconButton icon="plus" label="Add query" onClick={() => setQueries([...queries, ""])} />}
          <Button onClick={() => void search.run(true)} disabled={search.busy}>Search with these</Button>
        </div>
      )}

      {search.busy && <SkeletonCards n={3} />}
      {!search.busy && !receipt && (
        <EmptyState icon="search" title="Start with a claim"
          text="You will see the exact queries, the sources searched and what was not searched. Candidates are ordered by possible relevance, not quality, and carry no supports or contradicts label." />
      )}
      {!search.busy && receipt && (
        <div className="candidate-layout">
          <main>
            <div className="results-head">
              <div><b>{results.length} candidate {results.length === 1 ? "reference" : "references"}</b><span>Ordered by possible relevance, not quality. Possibly relevant: read the passage yourself.</span></div>
              <Disclaimer />
            </div>
            {results.length === 0
              ? <EmptyState icon="search" title="No candidates found" text="This does not mean nothing exists. Check the receipt for what was and was not searched, and try different queries." />
              : results.map((c) => <CandidateCard key={`${c.title}-${c.rank}`} c={c} saved={saved.has(c.title)} busy={save.busy} onSave={() => void save.run(c)} />)}
          </main>
          <aside><SearchReceiptBlock receipt={receipt} /></aside>
        </div>
      )}
      {saved.size > 0 && (
        <div className="flow-toast"><Icon name="check" /><span>{saved.size} saved to your reading list</span>
          <Link className="button button--ghost" to="/reading">Open reading list</Link></div>
      )}
    </div>
  );
}
