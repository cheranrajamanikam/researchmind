import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/api/client";
import { useApi } from "@/api/hooks";
import type { ReadingItem } from "@/api/types";
import { Boundary } from "@/components/states";
import { Button, EmptyState, IconButton, PageTitle, Pill } from "@/components/ui";
import { useApp, useProjectId } from "@/context/AppContext";
import { paperLabel, viewerLink } from "@/lib/format";

type Status = ReadingItem["status"];
const COLUMNS: { status: Status; title: string }[] = [
  { status: "to_read", title: "To read" },
  { status: "reading", title: "Reading" },
  { status: "read", title: "Read" },
];

function Card({ item, onChange, onDelete }: { item: ReadingItem; onChange: (patch: Partial<ReadingItem>) => void; onDelete: () => void }) {
  const [note, setNote] = useState(item.note);
  const next: Record<Status, { label: string; to: Status } | null> = {
    to_read: { label: "Start reading", to: "reading" },
    reading: { label: "Mark as read", to: "read" },
    read: null,
  };
  const step = next[item.status];
  return (
    <article className="reading-card">
      <div>
        <span className="chip-row">{item.tags.slice(0, 2).map((t) => <Pill key={t}>{t}</Pill>)}</span>
        <IconButton icon="trash" label="Remove from reading list" onClick={onDelete} />
      </div>
      <h3>{item.title}</h3>
      <p>{paperLabel(item.authors, item.year)}{item.venue ? ` · ${item.venue}` : ""}</p>
      {item.why && <p className="muted">“{item.why}”</p>}
      <label>My note
        <textarea value={note} placeholder="Add a note…" onChange={(e) => setNote(e.target.value)}
          onBlur={() => { if (note !== item.note) onChange({ note }); }} />
      </label>
      <div>
        {step ? <Button variant="ghost" onClick={() => onChange({ status: step.to })}>{step.label}</Button>
          : <Button variant="ghost" onClick={() => onChange({ status: "to_read" })}>Move back to read later</Button>}
        {item.paper_id ? <Link className="button button--ghost" to={viewerLink(item.paper_id)}>Open in viewer</Link>
          : item.url ? <a className="button button--ghost" href={item.url} target="_blank" rel="noreferrer">Open source</a> : null}
      </div>
    </article>
  );
}

export default function ReadingList() {
  const pid = useProjectId();
  const { toast } = useApp();
  const res = useApi((s) => api.get<ReadingItem[]>(`/projects/${pid}/reading`, s), [pid], pid > 0);

  const patch = async (id: number, body: Partial<ReadingItem>) => {
    try {
      const upd = await api.patch<ReadingItem>(`/reading/${id}`, body);
      res.setData((rows) => rows?.map((r) => (r.id === id ? upd : r)));
    } catch (e) { toast((e as Error).message, "error"); }
  };
  const remove = async (id: number) => {
    try {
      await api.del(`/reading/${id}`);
      res.setData((rows) => rows?.filter((r) => r.id !== id));
    } catch (e) { toast((e as Error).message, "error"); }
  };

  return (
    <div className="screen">
      <PageTitle title="Reading list" description="A focused queue for papers you want to evaluate yourself."
        actions={<Link className="button button--secondary" to="/references">Find references</Link>} />
      <Boundary res={res} empty={(d) => d.length === 0 ? (
        <EmptyState icon="book" title="Nothing queued yet"
          text="Save candidates from Find references or Prior-work audit and decide for yourself which to read."
          action={<Link className="button button--primary" to="/references">Find references</Link>} />
      ) : null}>
        {(items) => (
          <div className="reading-board">
            {COLUMNS.map((col) => {
              const rows = items.filter((i) => i.status === col.status);
              return (
                <section className="reading-column" key={col.status} aria-label={col.title}>
                  <div className="section-head"><div><h2>{col.title}</h2><p>{rows.length} {rows.length === 1 ? "paper" : "papers"}</p></div></div>
                  {rows.map((i) => <Card key={i.id} item={i} onChange={(b) => void patch(i.id, b)} onDelete={() => void remove(i.id)} />)}
                </section>
              );
            })}
          </div>
        )}
      </Boundary>
    </div>
  );
}
