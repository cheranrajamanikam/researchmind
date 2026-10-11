import { useRef, useState, type DragEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/api/client";
import { useAction } from "@/api/hooks";
import type { Paper } from "@/api/types";
import { Icon } from "@/components/Icon";
import { PaperJob } from "@/components/Job";
import { Banner, Button, PageTitle, Pill } from "@/components/ui";
import { OllamaBanner } from "@/components/states";
import { useApp, useProjectId } from "@/context/AppContext";
import { pluralize } from "@/lib/format";

interface Rejected { filename: string; reason: string }

export default function Upload() {
  const nav = useNavigate();
  const pid = useProjectId();
  const { jobs, refreshJobs, refreshProjects, settings, toast } = useApp();
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const [rejected, setRejected] = useState<Rejected[]>([]);

  const send = useAction(async (files: File[]) => {
    const form = new FormData();
    files.forEach((f) => form.append("files", f));
    const out = await api.upload<{ papers: Paper[]; rejected: Rejected[] }>(`/projects/${pid}/papers`, form);
    setRejected(out.rejected);
    if (out.papers.length) toast(`Added ${pluralize(out.papers.length, "paper")}. Processing continues locally.`);
    refreshJobs();
    void refreshProjects();
  });

  const take = (list: FileList | null) => {
    if (!list?.length) return;
    void send.run(Array.from(list));
    if (input.current) input.current.value = "";
  };
  const onDrop = (e: DragEvent) => { e.preventDefault(); setOver(false); take(e.dataTransfer.files); };
  const retry = async (id: number) => { await api.post(`/papers/${id}/retry`); refreshJobs(); };

  const running = jobs.filter((j) => j.job_state === "running").length;
  const queued = jobs.filter((j) => j.job_state === "queued").length;
  const noText = jobs.filter((j) => j.status === "no_text");
  const showQueue = jobs.length > 0;

  return (
    <div className="screen screen--narrow">
      <PageTitle title="Add papers" description="PDFs stay on this device. ResearchMind extracts text and builds the index locally." />
      <OllamaBanner />
      <input ref={input} type="file" accept="application/pdf,.pdf" multiple hidden onChange={(e) => take(e.target.files)} />

      <div className={`dropzone ${over ? "active" : ""}`} role="button" tabIndex={0} aria-label="Drop PDFs here or press Enter to choose files"
        onClick={() => input.current?.click()} onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") input.current?.click(); }}
        onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)} onDrop={onDrop}
        style={over ? { borderColor: "var(--accent)", background: "var(--accent-soft)" } : undefined}>
        <div className="dropzone__icon"><Icon name="upload" size={28} /></div>
        <h2>{send.busy ? "Uploading…" : "Drop PDFs here"}</h2>
        <p>or choose files from your computer</p>
        <Button variant="primary" disabled={send.busy}>Choose files</Button>
        <small>PDF · up to 100 MB each · multiple files supported</small>
      </div>
      {send.error && <p className="form-error" role="alert">{send.error}</p>}
      {rejected.map((r) => <Banner key={r.filename} tone="review" icon="help" title={`${r.filename} was not added`}>{r.reason}</Banner>)}
      {noText.length > 0 && (
        <Banner tone="review" icon="help" title="Some PDFs have no text layer">
          {noText.map((j) => j.filename).join(", ")} look{noText.length === 1 ? "s" : ""} like scanned images. ResearchMind does not do OCR yet, so these cannot be searched.
          Export a text-based PDF from the source if you can.
        </Banner>
      )}

      {showQueue && (
        <div className="upload-queue">
          <div className="section-head">
            <div><h2>Processing queue</h2><p>You can leave this page. Processing continues locally.</p></div>
            {(running > 0 || queued > 0) ? <Pill tone="blue">{running} running{queued ? ` · ${queued} queued` : ""}</Pill> : <Pill tone="teal">All done</Pill>}
          </div>
          {jobs.slice(0, 12).map((j) => <PaperJob key={j.id} paper={j} onRetry={retry} />)}
          <div className="queue-actions">
            <Button icon="plus" onClick={() => input.current?.click()}>Add more</Button>
            <Button onClick={() => nav("/papers")}>Open library</Button>
            <Button variant="primary" onClick={() => nav("/extraction")}>Review extracted fields</Button>
          </div>
        </div>
      )}

      <section className="privacy-note">
        <Icon name="wifi" />
        <div><b>Local processing</b>
          <p>Files, extracted text, and embeddings remain on this machine. Online discovery is currently {settings?.online_discovery ? "on, and only short search queries can leave your device" : "off"}.</p></div>
        <Button variant="ghost" onClick={() => nav("/settings")}>Review privacy settings</Button>
      </section>
    </div>
  );
}
