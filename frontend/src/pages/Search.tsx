import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "@/api/client";
import { useAction } from "@/api/hooks";
import type { SearchResponse } from "@/api/types";
import { HowComputed } from "@/components/Analysis";
import { EvidenceCard } from "@/components/Evidence";
import { Icon } from "@/components/Icon";
import { OllamaBanner, SkeletonCards } from "@/components/states";
import { Banner, Button, EmptyState, PageTitle } from "@/components/ui";
import { useApp, useProjectId } from "@/context/AppContext";
import { usePublishEvidence } from "@/context/EvidenceContext";

export default function Search() {
  const pid = useProjectId();
  const { project, ollama } = useApp();
  const [sp, setSp] = useSearchParams();
  const [query, setQuery] = useState(sp.get("q") ?? "");
  const [semantic, setSemantic] = useState(sp.get("mode") !== "keyword");
  const [scoped, setScoped] = useState(true);
  const [res, setRes] = useState<SearchResponse | null>(null);
  const [paperFilter, setPaperFilter] = useState("");
  const [yearFilter, setYearFilter] = useState("");
  const ran = useRef(false);

  const run = useAction(async (q: string, mode: "keyword" | "semantic", scope: boolean) => {
    const out = await api.post<SearchResponse>("/search", { query: q, mode, project_id: scope ? pid : null, k: 20 });
    setRes(out);
    setPaperFilter("");
    setYearFilter("");
  });

  const submit = () => {
    const q = query.trim();
    if (!q) return;
    setSp({ q, mode: semantic ? "semantic" : "keyword" }, { replace: true });
    void run.run(q, semantic ? "semantic" : "keyword", scoped);
  };

  useEffect(() => {
    if (!ran.current && sp.get("q") && pid) { ran.current = true; submit(); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pid]);

  const papers = useMemo(() => {
    const m = new Map<number, string>();
    res?.results.forEach((r) => m.set(r.paper_id, r.paper_title));
    return [...m.entries()];
  }, [res]);
  const years = useMemo(() => [...new Set((res?.results ?? []).map((r) => r.year).filter((y): y is number => y !== null))].sort((a, b) => b - a), [res]);
  const shown = (res?.results ?? []).filter((r) => (!paperFilter || String(r.paper_id) === paperFilter) && (!yearFilter || String(r.year) === yearFilter));
  usePublishEvidence(shown);

  return (
    <div className="screen">
      <PageTitle title="Search your evidence"
        description={`Search exact terms or meaning across ${project?.paper_count ?? 0} locally indexed papers.`} />
      <OllamaBanner />
      <div className="search-hero">
        <div className="searchbox">
          <Icon name="search" />
          <input aria-label="Search query" placeholder="e.g. How does retrieval depth affect citation faithfulness?" value={query}
            onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") submit(); }} />
          <Button variant="primary" onClick={submit} disabled={run.busy || !query.trim()}>Search</Button>
        </div>
        <div className="search-options">
          <div className="segmented" role="group" aria-label="Search mode">
            <button type="button" className={!semantic ? "active" : ""} aria-pressed={!semantic} onClick={() => setSemantic(false)}>Keyword</button>
            <button type="button" className={semantic ? "active" : ""} aria-pressed={semantic} onClick={() => setSemantic(true)}>Semantic</button>
          </div>
          <label><input type="checkbox" checked={scoped} onChange={(e) => setScoped(e.target.checked)} /> Search within current project</label>
          <span>Enter to search</span>
        </div>
      </div>
      {semantic && ollama && !ollama.reachable && (
        <Banner tone="review" icon="help" title="Semantic search needs Ollama">If it isn't reachable, ResearchMind falls back to keyword search and tells you.</Banner>
      )}

      {run.error && <p className="form-error" role="alert">{run.error}</p>}
      {run.busy && <SkeletonCards n={3} />}

      {!run.busy && !res && (
        <EmptyState icon="search" title="Ask what your papers say" text="Results are real passages from your PDFs with their page numbers. Nothing is summarised or invented." />
      )}

      {!run.busy && res && (
        <div className="results-layout">
          <main>
            {res.degraded && <Banner tone="info" icon="help" title="Showing keyword results">{res.degraded}</Banner>}
            <div className="results-head">
              <div><b>{shown.length} {shown.length === 1 ? "passage" : "passages"} found</b>
                <span>Ranked by {res.mode === "semantic" ? "semantic relevance" : "keyword match"} · {res.papers_searched} papers searched</span></div>
            </div>
            {res.results.length === 0 ? (
              <EmptyState icon="search" title="No matching passages"
                text={`Nothing in ${res.papers_searched} indexed ${res.papers_searched === 1 ? "paper" : "papers"} is close enough to “${res.query}”. This is reported as "not found", not guessed at. Try different words, or switch search mode.`} />
            ) : shown.map((c, i) => <EvidenceCard key={`${c.chunk_id ?? i}`} c={c} compact={i > 0} />)}
          </main>
          <aside className="filter-panel">
            <h3>Refine results</h3>
            <label>Paper
              <select value={paperFilter} onChange={(e) => setPaperFilter(e.target.value)}>
                <option value="">All papers in results</option>
                {papers.map(([id, t]) => <option key={id} value={id}>{t.length > 44 ? `${t.slice(0, 44)}…` : t}</option>)}
              </select>
            </label>
            <label>Published
              <select value={yearFilter} onChange={(e) => setYearFilter(e.target.value)}>
                <option value="">Any year</option>
                {years.map((y) => <option key={y} value={y}>{y}</option>)}
              </select>
            </label>
            <HowComputed label="How results are ranked" rows={[
              { label: "Mode", value: res.mode === "semantic" ? "Meaning-based: your question and every passage are compared as embeddings" : "Exact words: SQLite full-text search over every passage" },
              { label: "Scope", value: scoped ? `This project (${res.papers_searched} papers)` : `Whole library (${res.papers_searched} papers)` },
            ]} />
          </aside>
        </div>
      )}
    </div>
  );
}
