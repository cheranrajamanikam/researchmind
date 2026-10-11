import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import type { Resource } from "@/api/hooks";
import { useApp } from "@/context/AppContext";
import { Disclaimer, HowComputed } from "./Analysis";
import { Icon } from "./Icon";
import { Banner, Button, EmptyState, Pill } from "./ui";

export function Skeleton({ h = 14, w = "100%" }: { h?: number; w?: string | number }) {
  return <div className="skeleton" style={{ height: h, width: w }} aria-hidden="true" />;
}

export function SkeletonCards({ n = 3 }: { n?: number }) {
  return (
    <div className="skeleton-stack" role="status" aria-label="Loading">
      {Array.from({ length: n }, (_, i) => (
        <div className="skeleton-card" key={i}><Skeleton h={12} w="30%" /><Skeleton h={16} /><Skeleton h={16} w="80%" /></div>
      ))}
    </div>
  );
}

export function ErrorState({ message, onRetry, status }: { message: string; onRetry?: () => void; status?: number }) {
  const unreachable = status === 0;
  return (
    <div className="error-state" role="alert">
      <div className="empty-state__icon"><Icon name={unreachable ? "wifi" : "help"} size={24} /></div>
      <h3>{unreachable ? "Can't reach ResearchMind" : "That didn't load"}</h3>
      <p>{message}</p>
      {onRetry && <Button onClick={onRetry}>Try again</Button>}
    </div>
  );
}

/** Wraps a useApi() resource: skeleton while loading, a clear error with retry, then the content. */
export function Boundary<T>({
  res, children, skeleton, empty,
}: { res: Resource<T>; children: (data: T) => ReactNode; skeleton?: ReactNode; empty?: (data: T) => ReactNode | null }) {
  if (res.error && res.data === undefined) return <ErrorState message={res.error.message} status={res.error.status} onRetry={res.reload} />;
  if (res.data === undefined) return <>{skeleton ?? <SkeletonCards />}</>;
  const e = empty?.(res.data);
  return <>{e ?? children(res.data)}</>;
}

/** Shown on every screen that depends on the local model when Ollama is not reachable. */
export function OllamaBanner() {
  const { ollama, refreshOllama } = useApp();
  if (!ollama || ollama.reachable) return null;
  return (
    <Banner tone="offline" icon="wifi" title="Ollama is offline"
      action={<Button onClick={() => void refreshOllama()}>Check again</Button>}>
      Keyword search, your saved papers and every stored result still work. Semantic search, new answers and new extractions need Ollama.
      Start it with <code>ollama serve</code>{ollama.error ? ` (${ollama.error})` : ""}.
    </Banner>
  );
}

/** The calm, designed "Insufficient evidence" state: not an error. */
export function InsufficientEvidence({
  message, searched, onAsk, children,
}: { message: string; searched?: string; onAsk?: () => void; children?: ReactNode }) {
  return (
    <div className="insufficient">
      <div className="empty-state__icon"><Icon name="search" size={24} /></div>
      <Pill tone="amber">Insufficient evidence</Pill>
      <h2>Your library cannot support this answer yet</h2>
      <p>{message}</p>
      <div className="insufficient__actions">
        <Link className="button button--primary" to="/references">Find possibly relevant references</Link>
        {onAsk && <Button onClick={onAsk}>Rephrase the question</Button>}
      </div>
      {searched && <div className="boundary"><b>What was searched</b><span>{searched}</span></div>}
      <Disclaimer />
      {children ?? <HowComputed rows={[{ label: "Rule", value: "An answer is only written when retrieved passages clear a relevance threshold. Otherwise the system says so." }]} />}
    </div>
  );
}

export function NoPapers({ what = "this" }: { what?: string }) {
  return (
    <EmptyState icon="upload" title="Add papers first"
      text={`${what[0].toUpperCase()}${what.slice(1)} works on the papers in your project. Upload a few PDFs and they will be indexed on this device.`}
      action={<Link className="button button--primary" to="/upload">Add papers</Link>} />
  );
}
