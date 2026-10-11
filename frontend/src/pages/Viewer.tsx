import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api } from "@/api/client";
import { useApi } from "@/api/hooks";
import type { Paper, PaperFields, ReproResponse } from "@/api/types";
import { Agreement, HowComputed } from "@/components/Analysis";
import { EvidenceCard } from "@/components/Evidence";
import { Boundary } from "@/components/states";
import { Button, Pill } from "@/components/ui";
import { usePublishEvidence } from "@/context/EvidenceContext";

interface PageText { number: number; text: string }

/** Find the quote in the page text even when whitespace or line breaks differ. */
function locate(text: string, quote: string): [number, number] | null {
  const words = quote.replace(/[“”"]/g, "").trim().split(/\s+/).filter(Boolean).slice(0, 40);
  if (words.length < 2) return null;
  const esc = words.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const m = new RegExp(esc.join("\\s+"), "i").exec(text);
  return m ? [m.index, m.index + m[0].length] : null;
}

function PageBody({ text, quote, size }: { text: string; quote: string; size: number }) {
  const mark = useRef<HTMLElement>(null);
  const span = useMemo(() => (quote ? locate(text, quote) : null), [text, quote]);
  useEffect(() => { mark.current?.scrollIntoView({ block: "center", behavior: "smooth" }); }, [span, text]);
  if (!text.trim()) return <p className="muted">No text was extracted from this page.</p>;
  return (
    <div className="pdf-page--text" style={{ fontSize: size }}>
      {span ? <>{text.slice(0, span[0])}<mark className="highlight" ref={mark}>{text.slice(span[0], span[1])}</mark>{text.slice(span[1])}</> : text}
    </div>
  );
}

export default function Viewer() {
  const { id } = useParams();
  const pid = Number(id);
  const nav = useNavigate();
  const [sp, setSp] = useSearchParams();
  const quote = sp.get("q") ?? "";
  const [page, setPage] = useState(Math.max(1, Number(sp.get("page") ?? 1) || 1));
  const [zoom, setZoom] = useState(100);
  const [tab, setTab] = useState<"evidence" | "fields" | "checklist">("evidence");

  const paper = useApi((s) => api.get<Paper>(`/papers/${pid}`, s), [pid], Number.isFinite(pid));
  const pages = useApi((s) => api.get<PageText[]>(`/papers/${pid}/pages`, s), [pid], Number.isFinite(pid));
  const fields = useApi((s) => api.get<PaperFields>(`/papers/${pid}/fields`, s), [pid], tab === "fields" || tab === "evidence");
  const repro = useApi((s) => api.get<ReproResponse>(`/papers/${pid}/reproducibility`, s), [pid], tab === "checklist");

  useEffect(() => { const p = Number(sp.get("page")); if (p > 0) setPage(p); }, [sp]);

  const current = pages.data?.find((p) => p.number === page);
  const p = paper.data;
  const evidence = p && quote ? [{ paper_id: p.id, paper_title: p.title, authors: p.authors, year: p.year, page, quote }] : [];
  usePublishEvidence(evidence);

  const linked = fields.data?.fields.find((f) => f.quote && quote && (f.quote.includes(quote.slice(0, 40)) || quote.includes(f.quote.slice(0, 40))));
  const goto = (n: number, q = "") => {
    setPage(n);
    const next = new URLSearchParams();
    next.set("page", String(n));
    if (q) next.set("q", q);
    setSp(next, { replace: true });
  };

  return (
    <Boundary res={paper}>
      {(paperData) => (
        <div className="viewer">
          <div className="viewer__bar">
            <div>
              <Button variant="ghost" icon="arrow" onClick={() => nav(-1)}>Back</Button>
              <span className="divider" /><b title={paperData.title}>{paperData.title.length > 70 ? `${paperData.title.slice(0, 70)}…` : paperData.title}</b>
            </div>
            <div>
              <Button onClick={() => setZoom((z) => Math.max(70, z - 10))} title="Smaller text">−</Button>
              <span>{zoom}%</span>
              <Button onClick={() => setZoom((z) => Math.min(160, z + 10))} title="Larger text">+</Button>
              <a className="button button--secondary" href={api.paperFileUrl(paperData.id, page)} target="_blank" rel="noreferrer">Open original PDF</a>
            </div>
          </div>
          <div className="viewer__body">
            <aside className="thumbnails" aria-label="Pages">
              {Array.from({ length: paperData.page_count }, (_, i) => i + 1).map((n) => (
                <button key={n} type="button" className={page === n ? "active" : ""} aria-current={page === n ? "page" : undefined} onClick={() => goto(n)}>
                  <span className="tiny-page" />{n}
                </button>
              ))}
            </aside>
            <main className="pdf-stage">
              <div className="pdf-page">
                {page === 1 && (
                  <>
                    <div className="pdf-kicker">{[paperData.venue, paperData.year].filter(Boolean).join(" · ").toUpperCase() || "PAPER"}</div>
                    <h2>{paperData.title}</h2>
                    {paperData.authors && <p className="pdf-authors">{paperData.authors}</p>}
                  </>
                )}
                {pages.error ? <p className="form-error" role="alert">{pages.error.message}</p>
                  : !current ? <p className="muted">{pages.loading ? "Loading page…" : "This page has no stored text."}</p>
                  : <PageBody text={current.text} quote={quote} size={Math.round(13 * (zoom / 100))} />}
                <small className="page-number">{page} / {paperData.page_count}</small>
              </div>
            </main>
            <aside className="inspector">
              <div className="tabs" role="tablist">
                {(["evidence", "fields", "checklist"] as const).map((t) => (
                  <button key={t} role="tab" aria-selected={tab === t} className={tab === t ? "active" : ""} onClick={() => setTab(t)}>
                    {t === "evidence" ? "Evidence" : t === "fields" ? "Fields" : "Checklist"}
                  </button>
                ))}
              </div>
              <div className="inspector__content">
                {tab === "evidence" && (
                  <>
                    {quote ? (
                      <>
                        <Pill tone="teal">Selected highlight</Pill>
                        <h3>Evidence details</h3>
                        <EvidenceCard c={evidence[0]} compact highlighted />
                        {linked && <div className="field-pair"><span>Linked field</span><b>{linked.name}</b></div>}
                        {linked && <div className="field-pair"><span>Extraction status</span><b><Agreement status={linked.status} /></b></div>}
                        {!locate(current?.text ?? "", quote) && <p className="muted" style={{ fontSize: 11 }}>The exact wording was not found on this page. It may sit across a line or page break.</p>}
                      </>
                    ) : (
                      <p className="muted" style={{ fontSize: 12 }}>Open a quote from Search, an answer, or the extraction review and it is highlighted here on its exact page.</p>
                    )}
                    <HowComputed rows={[{ label: "Page text", value: "Extracted from the PDF text layer when the file was added." }]} />
                  </>
                )}
                {tab === "fields" && (
                  <Boundary res={fields}>
                    {(f) => (
                      <>
                        <Pill tone="blue">{f.accepted} accepted · {f.counts.verify} to verify</Pill>
                        {f.fields.length === 0 && <p className="muted" style={{ fontSize: 12 }}>No fields extracted yet.</p>}
                        {f.fields.map((x) => (
                          <div key={x.id} className="field-pair" style={{ display: "grid", gap: 4 }}>
                            <span>{x.name}</span>
                            <b>{x.value || "Not reported"}</b>
                            <Agreement status={x.status} />
                            {x.page && <button className="link-button" onClick={() => goto(x.page as number, x.quote)}>p. {x.page}: show quote</button>}
                          </div>
                        ))}
                        <Button onClick={() => nav("/extraction")}>Open extraction review</Button>
                      </>
                    )}
                  </Boundary>
                )}
                {tab === "checklist" && (
                  <Boundary res={repro}>
                    {(r) => (
                      <>
                        <Pill tone="neutral">{r.counts.reported ?? 0} reported · {r.counts.partial ?? 0} partial · {r.counts.missing ?? 0} not located</Pill>
                        {r.items.map((it) => (
                          <div key={it.item} className="field-pair" style={{ display: "grid", gap: 4 }}>
                            <span>{it.item}</span>
                            <b>{it.detail}</b>
                            <Pill tone={it.status === "reported" ? "teal" : "amber"}>{it.status === "missing" ? "Not located" : it.status}</Pill>
                            {it.page && <button className="link-button" onClick={() => goto(it.page as number, it.quote)}>p. {it.page}: show passage</button>}
                          </div>
                        ))}
                        <p className="muted" style={{ fontSize: 11 }}>{r.note}</p>
                      </>
                    )}
                  </Boundary>
                )}
              </div>
            </aside>
          </div>
        </div>
      )}
    </Boundary>
  );
}

