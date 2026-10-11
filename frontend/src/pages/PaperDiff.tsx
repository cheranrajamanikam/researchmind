import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api } from "@/api/client";
import { useAction } from "@/api/hooks";
import type { DiffResponse } from "@/api/types";
import { AnalysisTitle, HowComputed } from "@/components/Analysis";
import { Icon } from "@/components/Icon";
import { PaperChecklist, useProjectPapers } from "@/components/PaperPicker";
import { NoPapers, SkeletonCards } from "@/components/states";
import { Button, EmptyState } from "@/components/ui";
import { viewerLink } from "@/lib/format";

export default function PaperDiff() {
  const { res, ready, pid } = useProjectPapers();
  const nav = useNavigate();
  const [sp, setSp] = useSearchParams();
  const [selected, setSelected] = useState<number[]>(() => (sp.get("papers") ?? "").split(",").map(Number).filter(Boolean));
  const [diff, setDiff] = useState<DiffResponse | null>(null);
  const [highlight, setHighlight] = useState(true);
  const auto = useRef(false);

  const compare = useAction(async (ids: number[]) => {
    const r = await api.post<DiffResponse>(`/projects/${pid}/diff`, { paper_ids: ids });
    setDiff(r);
    setSp({ papers: ids.join(",") }, { replace: true });
  });

  useEffect(() => {
    if (!auto.current && selected.length >= 2 && pid) { auto.current = true; void compare.run(selected); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pid]);

  if (res.data && ready.length < 2) {
    return <div className="screen"><AnalysisTitle title="Paper diff" description="Compare reported setups cell by cell." />
      {ready.length === 0 ? <NoPapers what="paper diff" /> : <EmptyState icon="file" title="Add one more paper" text="A diff compares at least two indexed papers side by side." action={<Link className="button button--primary" to="/upload">Add papers</Link>} />}</div>;
  }

  return (
    <div className="screen screen--wide">
      <AnalysisTitle title="Paper diff" description="Compare reported setups cell by cell. Highlighting indicates difference, not superiority."
        actions={<Button variant="primary" disabled={selected.length < 2}
          onClick={() => nav(`/prediction?papers=${selected.join(",")}`)}>Start think-first comparison</Button>} />
      {res.data === undefined ? <SkeletonCards n={2} /> : (
        <>
          <PaperChecklist papers={ready} selected={selected} onChange={setSelected} />
          <div className="table-toolbar">
            <span className="muted">{selected.length < 2 ? "Choose at least two papers (up to six)." : `${selected.length} papers selected`}</span>
            <Button variant="primary" onClick={() => void compare.run(selected)} disabled={selected.length < 2 || compare.busy}>{compare.busy ? "Comparing…" : "Compare setups"}</Button>
          </div>
          {compare.error && <p className="form-error" role="alert">{compare.error}</p>}
          {diff && (
            <section className="table-panel diff-panel">
              <div className="difference-key">
                <span><i />Values differ</span><span><i className="missing" />Not reported</span>
                <label><input type="checkbox" checked={highlight} onChange={(e) => setHighlight(e.target.checked)} /> Highlight differences</label>
              </div>
              <div className="data-scroll">
                <table className="data-table diff-table">
                  <thead><tr><th>Setup field</th>{diff.papers.map((p) => <th key={p.id} title={p.title}>{p.label}</th>)}</tr></thead>
                  <tbody>
                    {diff.rows.map((r) => (
                      <tr key={r.field}>
                        <td><b>{r.field}</b></td>
                        {r.cells.map((c, i) => {
                          const missing = !c.value;
                          const cls = highlight && r.differs ? (missing ? "diff-missing" : "diff-cell") : "";
                          return (
                            <td key={i} className={cls}>
                              <div className="diff-value">
                                <span className={missing ? "muted" : ""}>{missing ? "Not reported" : c.value}</span>
                                {c.quote && c.page && (
                                  <Link className="quote-trigger" title={`“${c.quote}” · p. ${c.page}`} to={viewerLink(diff.papers[i].id, c.page, c.quote)}>
                                    <Icon name="book" size={13} /> p. {c.page}
                                  </Link>
                                )}
                              </div>
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="muted" style={{ padding: "0 16px" }}>{diff.note}</p>
              <HowComputed rows={[
                { label: "Source", value: "Setup fields from the Extraction review. Confirmed and edited values take priority over automatic ones." },
                { label: "Highlighting", value: "A row is highlighted when any two papers report different values, or when one omits the field. It does not say which is better." },
              ]} />
            </section>
          )}
        </>
      )}
    </div>
  );
}
