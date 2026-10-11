import { useState } from "react";
import { api } from "@/api/client";
import { useAction } from "@/api/hooks";
import type { OverclaimResponse } from "@/api/types";
import { AnalysisTitle, HowComputed } from "@/components/Analysis";
import { EvidenceCard } from "@/components/Evidence";
import { OllamaBanner } from "@/components/states";
import { Button, EmptyState, Pill } from "@/components/ui";
import { useProjectId } from "@/context/AppContext";

export default function Overclaim() {
  const pid = useProjectId();
  const [text, setText] = useState("");
  const [res, setRes] = useState<OverclaimResponse | null>(null);
  const [idx, setIdx] = useState(0);
  const [editing, setEditing] = useState(true);

  const analyze = useAction(async () => {
    const r = await api.post<OverclaimResponse>(`/projects/${pid}/overclaim`, { text });
    setRes(r);
    setIdx(0);
    setEditing(false);
  });

  const findings = res?.findings ?? [];
  const f = findings[idx];

  // Build the highlighted view of the draft from the sentence offsets the server returned.
  const parts: { text: string; i: number | null }[] = [];
  if (res) {
    let cur = 0;
    findings.forEach((x, i) => {
      if (x.start < cur || x.end > text.length) return;
      if (x.start > cur) parts.push({ text: text.slice(cur, x.start), i: null });
      parts.push({ text: text.slice(x.start, x.end), i });
      cur = x.end;
    });
    if (cur < text.length) parts.push({ text: text.slice(cur), i: null });
  }

  return (
    <div className="screen screen--wide">
      <AnalysisTitle title="Overclaim meter"
        description="Review strong wording against the evidence in your library. No score or verdict is assigned."
        actions={<>
          {!editing && <Button onClick={() => setEditing(true)}>Edit draft</Button>}
          {!editing && findings.length > 1 && <Button variant="primary" onClick={() => setIdx((idx + 1) % findings.length)}>Review next highlight</Button>}
        </>} />
      <OllamaBanner />
      {analyze.error && <p className="form-error" role="alert">{analyze.error}</p>}
      <div className="editor-split">
        <section className="draft-editor">
          <div className="editor-bar"><b>Your draft</b><span>{res && !editing ? `${findings.length} passages to review · ${res.sentences_checked} sentences checked` : "Paste a paragraph from your own writing"}</span></div>
          {editing ? (
            <>
              <textarea className="editor-content" aria-label="Draft text" style={{ width: "100%", minHeight: 280, resize: "vertical" }} value={text}
                placeholder="Paste a paragraph from your draft, for example: “Increasing retrieval depth always produces more faithful answers.”"
                onChange={(e) => setText(e.target.value)} />
              <div className="builder-foot">
                <span>Your draft is analysed on this device and is not stored.</span>
                <Button variant="primary" onClick={() => void analyze.run()} disabled={analyze.busy || !text.trim()}>{analyze.busy ? "Checking…" : "Check wording"}</Button>
              </div>
            </>
          ) : (
            <div className="editor-content" style={{ whiteSpace: "pre-wrap" }}>
              {parts.map((p, k) => p.i === null ? <span key={k}>{p.text}</span> : (
                <mark key={k}><button type="button" className="link-button" aria-current={p.i === idx}
                  style={{ font: "inherit", background: "none", border: 0, padding: 0, textAlign: "left", textDecoration: p.i === idx ? "underline" : "none" }}
                  onClick={() => setIdx(p.i as number)}>{p.text}</button></mark>
              ))}
            </div>
          )}
        </section>

        <aside className="claim-review" aria-live="polite">
          {!res || editing ? (
            <EmptyState icon="file" title="Nothing checked yet" text="Strong words like “always”, “proves”, “significantly” or “state-of-the-art” are compared with what your uploaded papers actually report. You get quotes and questions, not a grade." />
          ) : !f ? (
            <EmptyState icon="check" title="No strong wording found" text={`${res.sentences_checked} sentences were checked against a list of strong claim words. This does not mean every claim is supported.`} />
          ) : (
            <>
              <Pill tone="amber">Strong wording to review · {idx + 1} of {findings.length}</Pill>
              <h2>“{f.sentence}”</h2>
              <div className="wording-compare">
                <div><span>Draft wording</span><b>{f.wording.map((w) => w.term).join(", ")}</b></div>
                <div><span>Consider qualifying</span><b>{[...new Set(f.wording.map((w) => w.qualifier))].join("; ")}</b></div>
              </div>
              {f.facts.length > 0 && (
                <div className="review-prompt"><b>What your library shows</b>
                  <ul>{f.facts.map((x) => <li key={x.label}>{x.label}: {x.value}</li>)}</ul></div>
              )}
              {f.evidence.length > 0
                ? f.evidence.slice(0, 3).map((c, i) => <EvidenceCard key={i} c={c} compact />)
                : <p className="muted">No passage in your library was close enough to this sentence. That is shown as “not found”, not as a problem with the claim.</p>}
              <div className="review-prompt"><b>Questions for you</b><ul>{f.questions.map((q) => <li key={q}>{q}</li>)}</ul></div>
              <HowComputed rows={[
                { label: "Detection", value: "A fixed list of strong wording patterns, matched sentence by sentence. No language model decides what is flagged." },
                { label: "Evidence", value: "The closest passages in your library by hybrid search, plus counts such as datasets and sample sizes found in them." },
                { label: "Output", value: "Quotes and questions only. No score and no verdict." },
              ]} />
            </>
          )}
        </aside>
      </div>
    </div>
  );
}
