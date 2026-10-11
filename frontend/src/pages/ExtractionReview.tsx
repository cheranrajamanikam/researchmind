import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/api/client";
import { useAction, useApi } from "@/api/hooks";
import type { FieldRow, PaperFields, ProjectExtraction } from "@/api/types";
import { Agreement, AnalysisTitle, HowComputed } from "@/components/Analysis";
import { Icon } from "@/components/Icon";
import { downloadText } from "@/components/PaperPicker";
import { Boundary, NoPapers, OllamaBanner } from "@/components/states";
import { Button, EmptyState, IconButton, Modal } from "@/components/ui";
import { useApp, useProjectId } from "@/context/AppContext";
import { usePublishEvidence } from "@/context/EvidenceContext";
import { pct, viewerLink } from "@/lib/format";

type Entry = ProjectExtraction["papers"][number];

function FieldValue({ f }: { f: FieldRow }) {
  const differs = f.status === "verify" && f.pass_a.value && f.pass_b.value && f.pass_a.value !== f.pass_b.value;
  if (differs) {
    return (
      <div className="candidate-values">
        <span><small>PASS A</small>{f.pass_a.value}</span>
        <span><small>PASS B</small>{f.pass_b.value}</span>
      </div>
    );
  }
  return f.value ? <b>{f.value}</b> : <b className="muted">Not reported</b>;
}

export default function ExtractionReview() {
  const pid = useProjectId();
  const { toast } = useApp();
  const res = useApi((s) => api.get<ProjectExtraction>(`/projects/${pid}/extraction`, s), [pid], pid > 0);
  const [paperId, setPaperId] = useState<number | null>(null);
  const [verifyOnly, setVerifyOnly] = useState(false);
  const [editing, setEditing] = useState<FieldRow | null>(null);
  const [editValue, setEditValue] = useState("");

  const entries = res.data?.papers.filter((p) => p.paper.status.startsWith("ready")) ?? [];
  const entry: Entry | undefined = entries.find((p) => p.paper.id === paperId) ?? entries[0];
  const rows = useMemo(() => (entry?.fields ?? []).filter((f) => !verifyOnly || f.status === "verify"), [entry, verifyOnly]);
  usePublishEvidence(rows.filter((f) => f.quote && f.page).map((f) => ({
    paper_id: entry!.paper.id, paper_title: entry!.paper.title, authors: "", year: null, page: f.page as number, quote: f.quote, label: f.name,
  })));

  const apply = (pid2: number, upd: PaperFields) =>
    res.setData((d) => d && { ...d, papers: d.papers.map((p) => (p.paper.id === pid2 ? { ...p, ...upd } : p)) });

  const act = useAction(async (f: FieldRow, action: "confirm" | "reject" | "edit" | "reset", value?: string) => {
    const upd = await api.patch<PaperFields>(`/fields/${f.id}`, { action, value });
    apply(entry!.paper.id, upd);
  });
  const rerun = useAction(async () => {
    await api.post(`/papers/${entry!.paper.id}/extract`);
    res.reload();
    toast("Extraction finished");
  });

  const counts = entry?.counts;
  const exportCsv = () => {
    const q = (s: string) => `"${(s ?? "").replace(/"/g, '""')}"`;
    const lines = ["field,value,status,page,quote", ...(entry?.fields ?? []).map((f) => [q(f.name), q(f.value), f.status, f.page ?? "", q(f.quote)].join(","))];
    downloadText(`extraction-${entry?.paper.id}.csv`, lines.join("\n"), "text/csv");
  };

  return (
    <div className="screen screen--wide">
      <AnalysisTitle title="Extraction review"
        description="Confirm every extracted setup field against the quoted source before using it in comparisons."
        actions={<>
          <Link className="button button--secondary" to="/contradictions">View contradictions</Link>
          <Button onClick={() => void rerun.run()} disabled={rerun.busy || !entry}>{rerun.busy ? "Extracting…" : "Re-run extraction"}</Button>
        </>} />
      <OllamaBanner />
      {(act.error || rerun.error) && <p className="form-error" role="alert">{act.error || rerun.error}</p>}
      <Boundary res={res} empty={(d) => d.papers.length === 0 ? <NoPapers what="extraction review" /> : null}>
        {() => !entry ? <NoPapers what="extraction review" /> : (
          <>
            <section className="paper-context">
              <div className="paper-thumb"><span>{entry.paper.label.split("·")[1]?.trim() ?? ""}</span><b>{entry.paper.title.slice(0, 28)}</b><small>{entry.paper.label}</small></div>
              <div>
                <label className="field"><span className="sr-only">Paper</span>
                  <select value={entry.paper.id} onChange={(e) => setPaperId(Number(e.target.value))} aria-label="Paper to review">
                    {entries.map((p) => <option key={p.paper.id} value={p.paper.id}>{p.paper.label} · {p.paper.title}</option>)}
                  </select></label>
                <p>Both-passes agreement rate: <b>{entry.agreement_rate === null ? "n/a" : pct(entry.agreement_rate)}</b> · {entry.accepted} fields accepted automatically</p>
              </div>
              <div className="review-progress">
                <span>Review progress <b>{counts?.reviewed ?? 0} / {counts?.total ?? 0}</b></span>
                <div className="progress"><i style={{ width: `${counts?.total ? (counts.reviewed / counts.total) * 100 : 0}%` }} /></div>
              </div>
            </section>

            <div className="table-toolbar">
              <div className="segmented" role="group" aria-label="Filter fields">
                <button type="button" className={!verifyOnly ? "active" : ""} aria-pressed={!verifyOnly} onClick={() => setVerifyOnly(false)}>All fields <span>{counts?.total ?? 0}</span></button>
                <button type="button" className={verifyOnly ? "active" : ""} aria-pressed={verifyOnly} onClick={() => setVerifyOnly(true)}>Verify manually <span>{counts?.verify ?? 0}</span></button>
              </div>
              <div><Button icon="download" onClick={exportCsv}>Export</Button></div>
            </div>

            {rows.length === 0 ? (
              <EmptyState icon="check" title={verifyOnly ? "Nothing left to verify" : "No fields extracted yet"}
                text={verifyOnly ? "Every field on this paper has been agreed by both passes or reviewed by you." : "Run extraction to pull setup fields with their page and quote. This needs Ollama for the text fields."} />
            ) : (
              <section className="table-panel extraction-panel">
                <div className="data-scroll">
                  <table className="data-table extraction-table">
                    <thead><tr><th>Field</th><th>Extracted value</th><th>Source evidence</th><th>Agreement</th><th>Review</th></tr></thead>
                    <tbody>
                      {rows.map((f) => (
                        <tr key={f.id} className={f.status === "verify" ? "row-review" : ""}>
                          <td><b>{f.name}</b></td>
                          <td><FieldValue f={f} /></td>
                          <td>
                            {f.quote ? (
                              <div className="cell-quote"><q>{f.quote}</q>
                                <Link to={viewerLink(entry.paper.id, f.page, f.quote)}>p. {f.page} <Icon name="arrow" size={12} /></Link></div>
                            ) : <span className="muted">No supporting passage located.</span>}
                          </td>
                          <td><Agreement status={f.status} /></td>
                          <td>
                            <div className="row-actions">
                              <IconButton icon="check" label={`Confirm ${f.name}`} disabled={act.busy || !f.value} onClick={() => void act.run(f, "confirm")} />
                              <IconButton icon="file" label={`Edit ${f.name}`} onClick={() => { setEditing(f); setEditValue(f.value); }} />
                              <IconButton icon="close" label={`Reject ${f.name}`} disabled={act.busy} onClick={() => void act.run(f, "reject")} />
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <HowComputed rows={[
                  { label: "Pass A", value: "Deterministic: patterns, term lists and parsed tables. Result values are taken from tables first, then from text." },
                  { label: "Pass B", value: "A local language model constrained to a JSON schema. If Ollama is offline, this pass does not run and fields stay marked for review." },
                  { label: "Agreement", value: "A value is accepted automatically only when both passes agree and its quote is found verbatim on the cited page." },
                  { label: "Your review", value: "Confirm, edit and reject actions are stored and used to measure extraction accuracy." },
                ]} />
              </section>
            )}
          </>
        )}
      </Boundary>
      {editing && (
        <Modal title={`Correct “${editing.name}”`} onClose={() => setEditing(null)}
          actions={<>
            <Button onClick={() => setEditing(null)}>Cancel</Button>
            <Button variant="primary" disabled={!editValue.trim() || act.busy}
              onClick={async () => { await act.run(editing, "edit", editValue); setEditing(null); }}>Save correction</Button>
          </>}>
          <label className="field"><span>Corrected value</span>
            <input autoFocus value={editValue} maxLength={2000} onChange={(e) => setEditValue(e.target.value)} />
          </label>
          {editing.quote && <p className="muted">Source, p. {editing.page}: “{editing.quote}”</p>}
        </Modal>
      )}
    </div>
  );
}
