import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "@/api/client";
import { useAction, useApi } from "@/api/hooks";
import type { ProvDoc } from "@/api/types";
import { Icon } from "@/components/Icon";
import { Boundary } from "@/components/states";
import { Button, EmptyState, IconButton, PageTitle } from "@/components/ui";
import { useApp, useProjectId } from "@/context/AppContext";
import { relativeTime } from "@/lib/format";
import { addMark, overlaps, removeMarks, segments, shiftMarks, wordCount, type Span } from "@/lib/marks";

const EVENT_LABEL = { created: "Document created", edited: "Passage edited", ai_marked: "AI-assisted mark added", ai_unmarked: "AI-assisted mark removed" } as const;

function Editor({ doc, onSaved, onDeleted }: { doc: ProvDoc; onSaved: (d: ProvDoc) => void; onDeleted: () => void }) {
  const { toast } = useApp();
  const [title, setTitle] = useState(doc.title);
  const [content, setContent] = useState(doc.content);
  const [marks, setMarks] = useState<Span[]>(doc.marks.map((m) => ({ start: m.start, end: m.end })));
  const [sel, setSel] = useState<Span>({ start: 0, end: 0 });
  const area = useRef<HTMLTextAreaElement>(null);
  useEffect(() => { setTitle(doc.title); setContent(doc.content); setMarks(doc.marks.map((m) => ({ start: m.start, end: m.end }))); }, [doc.id, doc.updated_at]); // eslint-disable-line react-hooks/exhaustive-deps

  const dirty = title !== doc.title || content !== doc.content || JSON.stringify(marks) !== JSON.stringify(doc.marks.map((m) => ({ start: m.start, end: m.end })));
  const save = useAction(async () => {
    onSaved(await api.patch<ProvDoc>(`/provenance/${doc.id}`, { title, content, marks }));
    toast("Saved on this device");
  });

  const read = () => {
    const a = area.current;
    if (a) setSel({ start: a.selectionStart, end: a.selectionEnd });
  };
  // Trim whitespace so a mark covers words, not the spaces around them.
  const trimmed = (): Span | null => {
    const raw = content.slice(sel.start, sel.end);
    const lead = raw.length - raw.trimStart().length;
    const end = sel.end - (raw.length - raw.trimEnd().length);
    return end > sel.start + lead ? { start: sel.start + lead, end } : null;
  };
  const span = trimmed();
  const isMarked = span ? overlaps(marks, span) : false;
  const selectedWords = span ? wordCount(content.slice(span.start, span.end)) : 0;
  const parts = useMemo(() => segments(content, marks), [content, marks]);
  const markedWords = marks.reduce((n, m) => n + wordCount(content.slice(m.start, m.end)), 0);

  return (
    <section className="notes-editor">
      <div className="editor-bar">
        <div><input className="link-button" aria-label="Document title" value={title} maxLength={300} onChange={(e) => setTitle(e.target.value)} style={{ font: "inherit", fontWeight: 600, border: 0, background: "none" }} />
          <span>{dirty ? "Unsaved changes" : `Saved ${relativeTime(doc.updated_at)}`}</span></div>
        <div style={{ display: "flex", gap: 8 }}>
          <IconButton icon="trash" label="Delete document" onClick={onDeleted} />
          <Button variant="primary" onClick={() => void save.run()} disabled={!dirty || save.busy}>Save</Button>
        </div>
      </div>
      <textarea ref={area} className="editor-content" aria-label="Notes" style={{ width: "100%", minHeight: 240, resize: "vertical" }} value={content}
        placeholder="Write or paste your notes. Select a passage and mark it if you used AI assistance on it."
        onChange={(e) => { setMarks(shiftMarks(content, e.target.value, marks)); setContent(e.target.value); }}
        onSelect={read} onKeyUp={read} onMouseUp={read} />
      <div className="selection-toolbar">
        <Button variant={isMarked ? "primary" : "secondary"} disabled={!span}
          onClick={() => { if (span) setMarks(isMarked ? removeMarks(marks, span) : addMark(marks, span)); }}>
          <Icon name="file" size={14} />{isMarked ? "Remove AI-assisted mark" : "Mark AI-assisted"}
        </Button>
        <span>{span ? `Selected passage · ${selectedWords} ${selectedWords === 1 ? "word" : "words"}` : "Select a passage to mark it"}</span>
      </div>
      {marks.length > 0 && (
        <div className="editor-content" style={{ whiteSpace: "pre-wrap" }} aria-label="Marked passages preview">
          {parts.map((p, i) => <span key={i} className={p.marked ? "ai-marked" : ""}>{p.text}</span>)}
        </div>
      )}
      <p className="muted">{markedWords} of {wordCount(content)} words marked. Marks are descriptive metadata only.</p>
    </section>
  );
}

export default function Provenance() {
  const pid = useProjectId();
  const [sp, setSp] = useSearchParams();
  const list = useApi((s) => api.get<ProvDoc[]>(`/projects/${pid}/provenance`, s), [pid], pid > 0);
  const docId = Number(sp.get("doc")) || list.data?.[0]?.id || null;
  const detail = useApi((s) => api.get<ProvDoc>(`/provenance/${docId}`, s), [docId], docId !== null);

  const create = useAction(async () => {
    const d = await api.post<ProvDoc>(`/projects/${pid}/provenance`, { title: "Untitled notes", content: "" });
    list.reload();
    setSp({ doc: String(d.id) }, { replace: true });
  });
  const remove = async () => {
    if (!docId || !window.confirm("Delete this document and its marking history from this device?")) return;
    await api.del(`/provenance/${docId}`);
    setSp({}, { replace: true });
    list.reload();
  };
  const d = detail.data;

  return (
    <div className="screen screen--wide">
      <PageTitle title="Provenance log" description="Mark passages you used AI assistance on and export your own writing record."
        actions={<>
          {d && <Button icon="download" onClick={() => void api.download(`/provenance/${d.id}/export.csv`, `provenance-${d.id}.csv`)}>Export CSV</Button>}
          {d && <Button icon="download" onClick={() => void api.download(`/provenance/${d.id}/export.json`, `provenance-${d.id}.json`)}>Export JSON</Button>}
          <Button variant="primary" icon="plus" onClick={() => void create.run()} disabled={create.busy}>New document</Button>
        </>} />
      <div className="provenance-notice" role="note"><Icon name="help" /><b>This tool records your own marking. It does not detect AI text.</b></div>
      <Boundary res={list} empty={(rows) => rows.length === 0 ? (
        <EmptyState icon="file" title="No documents yet" text="Create a notes document, then mark any passage you wrote with AI assistance. The log is stored only on this device and can be exported."
          action={<Button variant="primary" onClick={() => void create.run()}>New document</Button>} />
      ) : null}>
        {(rows) => (
          <div className="provenance-layout">
            <div>
              {rows.length > 1 && (
                <label className="field"><span className="sr-only">Document</span>
                  <select value={docId ?? ""} onChange={(e) => setSp({ doc: e.target.value }, { replace: true })} aria-label="Choose document">
                    {rows.map((r) => <option key={r.id} value={r.id}>{r.title}</option>)}
                  </select></label>
              )}
              {d ? <Editor doc={d} onSaved={(x) => { detail.setData(x); list.reload(); }} onDeleted={() => void remove()} /> : null}
            </div>
            <aside className="provenance-side">
              <h2>Document summary</h2>
              <div className="provenance-stats">
                <div><strong>{d?.words ?? 0}</strong><span>total words</span></div>
                <div><strong>{d?.marked_words ?? 0}</strong><span>marked words</span></div>
              </div>
              <p>Marks are descriptive metadata only. No percentage is used as an authorship claim.</p>
              <h3>Recent activity</h3>
              {(d?.events ?? []).length === 0 && <p className="muted">No activity yet.</p>}
              {(d?.events ?? []).slice(0, 12).map((e) => (
                <div className="log-event" key={e.id}>
                  <i />
                  <div><b>{EVENT_LABEL[e.kind]}</b><span>{e.words} {e.words === 1 ? "word" : "words"}{e.passage ? ` · “${e.passage.slice(0, 40)}${e.passage.length > 40 ? "…" : ""}”` : ""}</span></div>
                  <small>{relativeTime(e.created_at)}</small>
                </div>
              ))}
            </aside>
          </div>
        )}
      </Boundary>
    </div>
  );
}
