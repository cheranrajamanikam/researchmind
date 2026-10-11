import { useNavigate } from "react-router-dom";
import type { Citation } from "@/api/types";
import { citationLabel, citationText, viewerLink } from "@/lib/format";
import { useApp } from "@/context/AppContext";
import { Icon } from "./Icon";
import { Button, IconButton, Pill } from "./ui";

export type EvidenceLike = Pick<Citation, "paper_id" | "paper_title" | "authors" | "year" | "page" | "quote"> & { n?: number; label?: string };

/** Adapt evidence that arrives with a ready-made label (diff cells, predictions, conflicts) to the card. */
export function evidenceFrom(e: { paper_id: number; label: string; page: number | null; quote: string }, title?: string): EvidenceLike {
  return { paper_id: e.paper_id, paper_title: title ?? e.label, authors: "", year: null, page: e.page ?? 1, quote: e.quote, label: e.label };
}

/** The design's Evidence Card. Every quote shown anywhere in the app goes through this component. */
export function EvidenceCard({
  c, compact = false, highlighted = false, onOpen,
}: { c: EvidenceLike; compact?: boolean; highlighted?: boolean; onOpen?: () => void }) {
  const nav = useNavigate();
  const { toast } = useApp();
  const open = () => {
    onOpen?.();
    nav(viewerLink(c.paper_id, c.page, c.quote));
  };
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(c.label ? `${c.label}, p. ${c.page}. ${c.paper_title}.` : citationText(c as Citation));
      toast("Citation copied");
    } catch {
      toast("Could not copy. Select the text and copy it manually.", "error");
    }
  };
  return (
    <article className={`evidence-card ${compact ? "evidence-card--compact" : ""} ${highlighted ? "evidence-card--highlighted" : ""}`}>
      <div className="evidence-card__top">
        <Pill tone={highlighted ? "amber" : "blue"}>p. {c.page}</Pill>
        <span>{c.n ? `[${c.n}] ` : ""}{c.label ?? citationLabel(c)}</span>
      </div>
      <blockquote>“{c.quote}”</blockquote>
      <div className="evidence-card__source">
        <span>{c.paper_title}</span>
        <div>
          <IconButton icon="copy" label="Copy citation" onClick={copy} />
          <Button variant="ghost" onClick={open}>Open in viewer <Icon name="arrow" size={14} /></Button>
        </div>
      </div>
    </article>
  );
}

/** Small numbered chip that scrolls to / highlights the matching excerpt. */
export function CitationChip({ n, onClick }: { n: number; onClick?: () => void }) {
  return <button type="button" className="citation" onClick={onClick} aria-label={`Excerpt ${n}`}>{n}</button>;
}
