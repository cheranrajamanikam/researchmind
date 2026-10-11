import { useRef, type ReactNode } from "react";
import type { Citation, Message } from "@/api/types";
import { Disclaimer, HowComputed } from "./Analysis";
import { CitationChip, EvidenceCard } from "./Evidence";
import { InsufficientEvidence } from "./states";
import { Banner } from "./ui";

const MARKER = /\[(\d+)\]/g;

function withChips(line: string, onChip: (n: number) => void): ReactNode[] {
  const out: ReactNode[] = [];
  let last = 0;
  for (const m of line.matchAll(MARKER)) {
    const idx = m.index ?? 0;
    if (idx > last) out.push(line.slice(last, idx));
    out.push(<CitationChip key={`${idx}-${m[1]}`} n={Number(m[1])} onClick={() => onChip(Number(m[1]))} />);
    last = idx + m[0].length;
  }
  if (last < line.length) out.push(line.slice(last));
  return out;
}

/** Renders the assistant's text, turning [n] markers into chips that jump to the real excerpt below. */
function AnswerText({ content, onChip }: { content: string; onChip: (n: number) => void }) {
  const lines = content.split("\n").map((l) => l.trim()).filter(Boolean);
  const bullets = lines.filter((l) => l.startsWith("•"));
  const prose = lines.filter((l) => !l.startsWith("•"));
  return (
    <>
      {prose.map((l, i) => <p key={i}>{withChips(l, onChip)}</p>)}
      {bullets.length > 0 && <ol>{bullets.map((l, i) => <li key={i}>{withChips(l.replace(/^•\s*/, ""), onChip)}</li>)}</ol>}
    </>
  );
}

export function AssistantMessage({
  message, onRephrase, compact = false, searched,
}: { message: Message; onRephrase?: () => void; compact?: boolean; searched?: string }) {
  const refs = useRef<Record<number, HTMLDivElement | null>>({});
  const jump = (n: number) => refs.current[n]?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  const cites: Citation[] = message.citations ?? [];
  const papers = new Set(cites.map((c) => c.paper_id)).size;
  const took = typeof message.meta?.took_s === "number" ? `${message.meta.took_s}s` : null;
  const model = typeof message.meta?.model === "string" ? message.meta.model : null;

  if (message.status === "insufficient") {
    return <InsufficientEvidence message={message.content} searched={searched} onAsk={onRephrase} />;
  }

  const offline = message.status === "offline" || message.status === "extractive";
  const reading = message.status === "reading";
  const head = reading ? "Reading mode" : offline ? "Passages only (model offline)" : "Evidence-led answer";
  const sub = `${reading ? "Pointed to" : "Answered from"} ${papers} ${papers === 1 ? "paper" : "papers"} · ${cites.length} ${cites.length === 1 ? "passage" : "passages"}`;

  return (
    <div className={compact ? "copilot-answer" : "answer"}>
      <div className="answer__head">
        <span className="rm-mark">R</span>
        <div><b>{head}</b><small>{sub}</small></div>
        <Disclaimer />
      </div>
      <div className={compact ? undefined : "answer__body"}>
        {offline && (
          <Banner tone="offline" icon="wifi" title="The local model was not available">
            These are the most relevant passages from your library, shown as they are. No summary was written.
          </Banner>
        )}
        <AnswerText content={message.content} onChip={jump} />
        {cites.map((c, i) => (
          <div key={`${c.chunk_id ?? i}-${c.n ?? i}`} ref={(el) => { refs.current[c.n ?? i + 1] = el; }}>
            <EvidenceCard c={c} compact />
          </div>
        ))}
        <HowComputed
          completedAt={message.created_at}
          rows={[
            { label: "Retrieval", value: "Hybrid keyword + semantic search over your indexed passages" },
            { label: "Citations", value: "Written by the backend from the retrieved passages. The model only says which excerpt numbers it used." },
            ...(model ? [{ label: "Answer model", value: `${model}${took ? ` · ${took}` : ""}` }] : []),
          ]}
        />
      </div>
    </div>
  );
}

export function UserMessage({ name, message }: { name: string; message: Message }) {
  const initials = name.trim().split(/\s+/).map((p) => p[0]).slice(0, 2).join("").toUpperCase() || "ME";
  return (
    <div className="user-prompt">
      <span>{initials}</span>
      <div>
        <small>You · {new Date(message.created_at).toLocaleString(undefined, { hour: "2-digit", minute: "2-digit", day: "numeric", month: "short" })}</small>
        <p>{message.content}</p>
      </div>
    </div>
  );
}
