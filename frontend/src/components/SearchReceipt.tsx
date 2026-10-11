import type { Receipt } from "@/api/types";
import { dateTime } from "@/lib/format";
import { HowComputed } from "./Analysis";
import { Icon } from "./Icon";
import { Pill } from "./ui";

const n = (v: unknown): number | string => (typeof v === "number" || typeof v === "string" ? v : 0);

/** The Search Receipt block: what was searched, where, when, and what was NOT covered. */
export function SearchReceiptBlock({ receipt, expanded = false }: { receipt: Receipt; expanded?: boolean }) {
  const c = receipt.counts;
  const shown = expanded ? receipt.queries : receipt.queries.slice(0, 2);
  return (
    <section className="receipt" aria-label="Search receipt">
      <div className="receipt__head">
        <div>
          <span className="receipt-mark"><Icon name="search" size={17} /></span>
          <div><h3>Search receipt</h3><p>Permanent record · {dateTime(receipt.created_at)}</p></div>
        </div>
        <Pill tone={receipt.online ? "blue" : "neutral"}>{receipt.online ? "Online discovery" : "Local library only"}</Pill>
      </div>
      <div className="receipt__grid">
        <div><span>Queries run</span><b>{n(c.queries)}</b></div>
        <div><span>Sources searched</span><b>{n(c.sources_searched)}</b></div>
        <div><span>Results screened</span><b>{n(c.titles_screened)}</b></div>
        <div><span>Candidate papers</span><b>{n(c.candidates)}</b></div>
      </div>
      <div className="receipt__section">
        <b>Queries run</b>
        {shown.map((q) => <code key={q}>{q}</code>)}
        {!expanded && receipt.queries.length > shown.length && <span className="muted">+{receipt.queries.length - shown.length} more in the full receipt</span>}
      </div>
      <div className="receipt__columns">
        <div>
          <b>Sources searched</b>
          {receipt.sources_searched.map((s) => <span key={s}><Icon name="check" size={13} /> {s}</span>)}
        </div>
        <div>
          <b>Not searched</b>
          {receipt.sources_not_searched.map((s) => <span key={s}>{s}</span>)}
        </div>
      </div>
      <div className="receipt__notice"><Icon name="help" size={15} /><b>{receipt.notice || "Absence of results is not evidence of novelty."}</b></div>
      <HowComputed label="Search method and filters" completedAt={receipt.created_at}
        rows={[
          { label: "Ranking", value: String(c.rank_method ?? "local embeddings") },
          { label: "Sent off this device", value: receipt.online ? "Short search queries only (shown above). Never paper text." : "Nothing" },
        ]} />
    </section>
  );
}
