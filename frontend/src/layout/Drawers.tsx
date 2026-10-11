import { useEffect, useRef, useState } from "react";
import { api } from "@/api/client";
import type { Message } from "@/api/types";
import { useAction } from "@/api/hooks";
import { HowComputed } from "@/components/Analysis";
import { AssistantMessage } from "@/components/Answer";
import { EvidenceCard } from "@/components/Evidence";
import { Icon } from "@/components/Icon";
import { Button, IconButton, Switch } from "@/components/ui";
import { useApp } from "@/context/AppContext";
import { useEvidencePanel } from "@/context/EvidenceContext";

export function EvidenceDrawer() {
  const { setEvidenceOpen } = useApp();
  const { items } = useEvidencePanel();
  return (
    <aside className="evidence-drawer" aria-label="Evidence panel" onKeyDown={(e) => { if (e.key === "Escape") setEvidenceOpen(false); }}>
      <div className="drawer-head">
        <div><span>Evidence panel</span><b>{items.length} {items.length === 1 ? "item" : "items"} in view</b></div>
        <IconButton icon="close" label="Close panel" onClick={() => setEvidenceOpen(false)} />
      </div>
      <div className="drawer-body">
        {items.length === 0
          ? <p>Passages from the page you are on (search results, an answer, a comparison) collect here so you can keep them beside your work.</p>
          : <>
              <p>Evidence connected to your current view.</p>
              {items.slice(0, 12).map((c, i) => <EvidenceCard key={`${c.paper_id}-${c.page}-${i}`} c={c} compact onOpen={() => setEvidenceOpen(false)} />)}
            </>}
        <HowComputed rows={[{ label: "Source", value: "Each passage is stored text from your PDF with its page number." }]} />
      </div>
    </aside>
  );
}

interface Turn { question: string; reading: boolean; reply?: Message; error?: string; pending: boolean }

export function CopilotDrawer() {
  const { setCopilotOpen, project, userName } = useApp();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [text, setText] = useState("");
  const [reading, setReading] = useState(false);
  const bottom = useRef<HTMLDivElement>(null);

  const ask = useAction(async (question: string, readingMode: boolean) => {
    if (!project) throw new Error("Create a project first.");
    return api.post<{ assistant: Message }>("/copilot/ask", { project_id: project.id, question, reading_mode: readingMode });
  });

  useEffect(() => { bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [turns]);

  const submit = async () => {
    const q = text.trim();
    if (!q || ask.busy) return;
    setText("");
    setTurns((t) => [...t, { question: q, reading, pending: true }]);
    const out = await ask.run(q, reading);
    setTurns((t) => t.map((x, i) => i === t.length - 1
      ? { ...x, pending: false, reply: out?.assistant, error: out ? undefined : "The question could not be answered. Check the server and try again." }
      : x));
  };

  return (
    <aside className="evidence-drawer copilot-drawer" aria-label="Research copilot" onKeyDown={(e) => { if (e.key === "Escape") setCopilotOpen(false); }}>
      <div className="drawer-head">
        <div><span>Research copilot</span><b>{project?.name ?? "No project"}</b></div>
        <IconButton icon="close" label="Close copilot" onClick={() => setCopilotOpen(false)} />
      </div>
      <div className="drawer-body">
        <div className="copilot-scope">
          <Icon name="archive" size={15} />
          <span>Answers use {project?.paper_count ?? 0} {project?.paper_count === 1 ? "paper" : "papers"} in this project</span>
        </div>
        <label className="switch-label" style={{ justifyContent: "space-between" }}>
          Reading mode <small className="muted">points to what to read instead of summarising</small>
          <Switch checked={reading} onChange={setReading} label="Reading mode" />
        </label>

        {turns.length === 0 && <p>Ask a question about the papers in this project. Every answer cites the real page and passage, or says the evidence isn't there.</p>}
        {turns.map((t, i) => (
          <div key={i}>
            <div className="copilot-question" title={userName}>{t.question}</div>
            {t.pending && <div className="job" role="status"><span className="spinner" /><div className="job__main"><span>Searching your papers…</span></div></div>}
            {t.error && <p className="form-error" role="alert">{t.error}</p>}
            {t.reply && <AssistantMessage message={t.reply} compact />}
          </div>
        ))}
        <div ref={bottom} />

        <div className="composer">
          <textarea aria-label="Ask research copilot" placeholder="Ask your project evidence…" value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void submit(); } }} />
          <div>
            <span>Enter to ask · Shift Enter for line break</span>
            <Button variant="primary" icon="arrow" onClick={() => void submit()} disabled={ask.busy || !text.trim() || !project}>Ask</Button>
          </div>
        </div>
      </div>
    </aside>
  );
}
