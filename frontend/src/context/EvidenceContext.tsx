import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import type { EvidenceLike } from "@/components/Evidence";

interface Ctx { items: EvidenceLike[]; setItems: (v: EvidenceLike[]) => void }
const EvidenceCtx = createContext<Ctx | null>(null);

export function EvidenceProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<EvidenceLike[]>([]);
  const value = useMemo(() => ({ items, setItems }), [items]);
  return <EvidenceCtx.Provider value={value}>{children}</EvidenceCtx.Provider>;
}

export function useEvidencePanel(): Ctx {
  const c = useContext(EvidenceCtx);
  if (!c) throw new Error("useEvidencePanel must be used inside <EvidenceProvider>");
  return c;
}

/** A page calls this with the passages currently in view; the right-hand Evidence panel shows them. */
export function usePublishEvidence(items: EvidenceLike[] | undefined): void {
  const { setItems } = useEvidencePanel();
  const key = items ? items.map((i) => `${i.paper_id}:${i.page}:${i.quote.slice(0, 24)}`).join("|") : "";
  useEffect(() => {
    setItems(items ?? []);
    return () => setItems([]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
}
