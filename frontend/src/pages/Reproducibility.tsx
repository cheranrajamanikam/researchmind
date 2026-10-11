import { Link } from "react-router-dom";
import { api } from "@/api/client";
import { useApi } from "@/api/hooks";
import type { ReproResponse } from "@/api/types";
import { AnalysisTitle, HowComputed } from "@/components/Analysis";
import { Icon } from "@/components/Icon";
import { downloadText, PaperSelect, usePaperParam, useProjectPapers } from "@/components/PaperPicker";
import { Boundary, NoPapers, SkeletonCards } from "@/components/states";
import { Button, Pill } from "@/components/ui";
import { viewerLink } from "@/lib/format";

const LABEL = { reported: "Reported", partial: "Partially reported", missing: "Not located" } as const;

export default function Reproducibility() {
  const { res, ready } = useProjectPapers();
  const [paperId, setPaperId] = usePaperParam(ready);
  const out = useApi((s) => api.get<ReproResponse>(`/papers/${paperId}/reproducibility`, s), [paperId], paperId !== null);

  const exportCsv = (d: ReproResponse) => {
    const q = (s: string) => `"${(s ?? "").replace(/"/g, '""')}"`;
    downloadText(`reproducibility-${d.paper_id}.csv`,
      ["item,status,detail,page,quote", ...d.items.map((i) => [q(i.item), i.status, q(i.detail), i.page ?? "", q(i.quote)].join(","))].join("\n"), "text/csv");
  };

  return (
    <div className="screen">
      <AnalysisTitle title="Reproducibility X-ray" description="A source-linked view of what the paper reports and what could not be located."
        actions={out.data && <Button icon="download" onClick={() => exportCsv(out.data!)}>Export checklist</Button>} />
      {res.data === undefined ? <SkeletonCards n={2} /> : ready.length === 0 ? <NoPapers what="the reproducibility X-ray" /> : (
        <>
          <PaperSelect papers={ready} value={paperId} onChange={setPaperId} />
          <Boundary res={out} skeleton={<SkeletonCards n={2} />}>
            {(d) => (
              <>
                <div className="xray-summary">
                  <div><strong>{d.counts.reported ?? 0}</strong><span>Reported</span></div>
                  <div><strong>{d.counts.partial ?? 0}</strong><span>Partially reported</span></div>
                  <div><strong>{d.counts.missing ?? 0}</strong><span>Not located</span></div>
                  <p>“Not located” means the analysis did not find supporting text. Verify the paper and its supplements manually.</p>
                </div>
                <section className="table-panel">
                  <div className="data-scroll">
                    <table className="data-table">
                      <thead><tr><th>Reproducibility item</th><th>Status</th><th>Reported detail</th><th>Evidence</th></tr></thead>
                      <tbody>
                        {d.items.map((r) => (
                          <tr key={r.item}>
                            <td><b>{r.item}</b></td>
                            <td><Pill tone={r.status === "reported" ? "teal" : "amber"}>{r.status === "reported" && <Icon name="check" size={11} />}{LABEL[r.status]}</Pill></td>
                            <td>{r.detail || <span className="muted">—</span>}</td>
                            <td>{r.page
                              ? <Link className="button button--ghost" to={viewerLink(d.paper_id, r.page, r.quote)}>p. {r.page} <Icon name="arrow" size={12} /></Link>
                              : <span className="muted">No passage</span>}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  <HowComputed rows={[
                    { label: "Method", value: "Pattern matching over the paper's own text (code links, seeds, hardware, splits, hyperparameters, limitations). Presence or absence of text is checked, not whether the work is reproducible." },
                    { label: "Limit", value: d.note },
                  ]} />
                </section>
              </>
            )}
          </Boundary>
        </>
      )}
    </div>
  );
}
