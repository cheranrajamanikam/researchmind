import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "@/api/client";
import { useAction, useApi } from "@/api/hooks";
import type { Message, Thread } from "@/api/types";
import { AssistantMessage, UserMessage } from "@/components/Answer";
import { Icon } from "@/components/Icon";
import { Boundary, OllamaBanner, SkeletonCards } from "@/components/states";
import { Banner, Button, EmptyState, IconButton, Modal, PageTitle, Pill, Switch } from "@/components/ui";
import { useApp } from "@/context/AppContext";
import { usePublishEvidence } from "@/context/EvidenceContext";
import { pluralize, relativeTime } from "@/lib/format";

type View = "all" | "starred" | "follow";

export function Threads() {
  const nav = useNavigate();
  const { projects, project, toast } = useApp();
  const res = useApi((s) => api.get<Thread[]>("/threads", s), []);
  const [view, setView] = useState<View>("all");
  const [scope, setScope] = useState<number | "all">(project?.id ?? "all");
  const [q, setQ] = useState("");
  const [sort, setSort] = useState<"recent" | "title">("recent");

  const create = useAction(async () => {
    if (!project) throw new Error("Create a project first.");
    const t = await api.post<Thread>("/threads", { project_id: scope === "all" ? project.id : scope, title: "New thread" });
    nav(`/threads/${t.id}`);
  });
  const star = async (t: Thread) => {
    try { await api.patch(`/threads/${t.id}`, { starred: !t.starred }); res.reload(); } catch (e) { toast((e as Error).message, "error"); }
  };

  const all = res.data ?? [];
  const inScope = all.filter((t) => scope === "all" || t.project_id === scope);
  const counts = { all: inScope.length, starred: inScope.filter((t) => t.starred).length, follow: inScope.filter((t) => t.last_status === "insufficient").length };
  const shown = inScope
    .filter((t) => (view === "starred" ? t.starred : view === "follow" ? t.last_status === "insufficient" : true))
    .filter((t) => !q || t.title.toLowerCase().includes(q.toLowerCase()))
    .sort((a, b) => (sort === "title" ? a.title.localeCompare(b.title) : b.updated_at.localeCompare(a.updated_at)));
  const projectName = (id: number) => projects.find((p) => p.id === id)?.name ?? "Unknown project";

  return (
    <div className="screen">
      <PageTitle title="Threads" description="Questions, cited answers, and your notes, kept together as a research trail."
        actions={<Button variant="primary" icon="plus" onClick={() => void create.run()} disabled={create.busy}>New thread</Button>} />
      {create.error && <p className="form-error" role="alert">{create.error}</p>}
      <div className="thread-layout">
        <aside className="thread-filters">
          <b>Views</b>
          <button className={view === "all" ? "active" : ""} onClick={() => setView("all")}>All threads <span>{counts.all}</span></button>
          <button className={view === "starred" ? "active" : ""} onClick={() => setView("starred")}>Starred <span>{counts.starred}</span></button>
          <button className={view === "follow" ? "active" : ""} onClick={() => setView("follow")}>Needs follow-up <span>{counts.follow}</span></button>
          <b>Projects</b>
          <button className={scope === "all" ? "active" : ""} onClick={() => setScope("all")}>All projects <span>{all.length}</span></button>
          {projects.map((p) => <button key={p.id} className={scope === p.id ? "active" : ""} onClick={() => setScope(p.id)}>{p.name} <span>{all.filter((t) => t.project_id === p.id).length}</span></button>)}
        </aside>
        <main className="thread-list">
          <div className="toolbar">
            <div className="field field--search"><Icon name="search" size={16} /><input placeholder="Search threads…" aria-label="Search threads" value={q} onChange={(e) => setQ(e.target.value)} /></div>
            <select className="select-like" aria-label="Sort" value={sort} onChange={(e) => setSort(e.target.value as "recent" | "title")}><option value="recent">Recently updated</option><option value="title">Title</option></select>
          </div>
          <Boundary res={res} skeleton={<SkeletonCards n={4} />}>
            {() => shown.length === 0 ? (
              <EmptyState icon="thread" title={all.length === 0 ? "No threads yet" : "No threads here"} text="Ask a question about your papers. The answer, its citations and your follow-ups are saved as a thread."
                action={<Button variant="primary" onClick={() => void create.run()}>New thread</Button>} />
            ) : <>{shown.map((t) => {
              const insufficient = t.last_status === "insufficient";
              return (
                <article className="thread-row" key={t.id} tabIndex={0} onClick={() => nav(`/threads/${t.id}`)} onKeyDown={(e) => { if (e.key === "Enter") nav(`/threads/${t.id}`); }}>
                  <div className="thread-row__icon"><Icon name="thread" /></div>
                  <div>
                    <h3>{t.title}</h3>
                    <p>{t.message_count === 0 ? "No questions asked yet" : insufficient ? "Insufficient evidence in your library" : `Answered · ${pluralize(t.last_citations, "evidence passage")}`}</p>
                    <span>{projectName(t.project_id)}</span>
                  </div>
                  {insufficient && <Pill tone="amber">Follow up</Pill>}
                  <time>{relativeTime(t.updated_at)}</time>
                  <span onClick={(e) => e.stopPropagation()}><IconButton icon="star" label={t.starred ? "Unstar thread" : "Star thread"} onClick={() => void star(t)} /></span>
                  <Icon name="chevron" />
                </article>
              );
            })}</>}
          </Boundary>
        </main>
      </div>
    </div>
  );
}

export function ThreadDetail() {
  const { id } = useParams();
  const tid = Number(id);
  const nav = useNavigate();
  const { projects, userName, toast, project } = useApp();
  const res = useApi((s) => api.get<Thread>(`/threads/${tid}`, s), [tid]);
  const [msgs, setMsgs] = useState<Message[]>([]);
  const [text, setText] = useState("");
  const [reading, setReading] = useState(false);
  const [pending, setPending] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const box = useRef<HTMLTextAreaElement>(null);
  const bottom = useRef<HTMLDivElement>(null);

  useEffect(() => { if (res.data?.messages) setMsgs(res.data.messages); }, [res.data]);
  useEffect(() => { bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [msgs.length, pending]);
  const lastAnswer = [...msgs].reverse().find((m) => m.role === "assistant");
  usePublishEvidence(lastAnswer?.citations ?? []);

  const ask = useAction(async (content: string) => {
    setPending(content);
    try {
      const out = await api.post<{ user: Message; assistant: Message }>(`/threads/${tid}/messages`, { content, reading_mode: reading });
      setMsgs((m) => [...m, out.user, out.assistant]);
      res.reload();
    } finally { setPending(null); }
  });
  const submit = async () => {
    const c = text.trim();
    if (!c || ask.busy) return;
    setText("");
    await ask.run(c);
  };
  const del = useAction(async () => { await api.del(`/threads/${tid}`); toast("Thread deleted"); nav("/threads"); });

  const thread = res.data;
  const owner = projects.find((p) => p.id === thread?.project_id) ?? project;
  const papers = owner?.paper_count ?? 0;

  return (
    <Boundary res={res}>
      {(t) => (
        <div className="thread-detail">
          <div className="thread-top">
            <div><Button variant="ghost" icon="arrow" onClick={() => nav("/threads")}>Threads</Button><span className="divider" /><b>{t.title}</b></div>
            <div>
              <label className="switch-label">Reading mode <Switch checked={reading} onChange={setReading} label="Reading mode" /></label>
              <IconButton icon="trash" label="Delete thread" onClick={() => setConfirmDelete(true)} />
            </div>
          </div>
          <div className="conversation">
            <OllamaBanner />
            {reading && <Banner tone="info" icon="book" title="Reading mode is on">Answers point you to what to read and compare instead of summarising it for you.</Banner>}
            {msgs.length === 0 && !pending && <EmptyState icon="thread" title="Ask your first question" text="Answers cite the real page and passage. If your papers don't contain the evidence, you'll be told that instead." />}
            {msgs.map((m) => m.role === "user"
              ? <UserMessage key={m.id} name={userName} message={m} />
              : <AssistantMessage key={m.id} message={m} onRephrase={() => box.current?.focus()} searched={`${papers} local papers · semantic and keyword retrieval · ${m.citations.length} related passages`} />)}
            {pending && (
              <>
                <div className="user-prompt"><span>{userName.slice(0, 2).toUpperCase() || "ME"}</span><div><small>You · just now</small><p>{pending}</p></div></div>
                <div className="job" role="status"><span className="spinner" /><div className="job__main"><span>Searching your papers and checking the evidence…</span></div></div>
              </>
            )}
            {ask.error && <p className="form-error" role="alert">{ask.error}</p>}
            <div ref={bottom} />
            <div className="composer">
              <textarea ref={box} aria-label="Ask your papers" placeholder={msgs.length ? "Ask a follow-up question…" : "Ask a question about your papers…"} value={text}
                onChange={(e) => setText(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); void submit(); } }} />
              <div>
                <span><Icon name="archive" size={15} /> {owner?.name ?? "Project"} · {pluralize(papers, "paper")}</span>
                <Button variant="primary" icon="arrow" onClick={() => void submit()} disabled={ask.busy || !text.trim()}>Ask</Button>
              </div>
            </div>
          </div>
          {confirmDelete && (
            <Modal title="Delete this thread?" onClose={() => setConfirmDelete(false)}
              actions={<><Button onClick={() => setConfirmDelete(false)}>Cancel</Button><Button variant="danger" onClick={() => void del.run()} disabled={del.busy}>Delete thread</Button></>}>
              <p>The questions and answers in “{t.title}” are removed from this device.</p>
            </Modal>
          )}
        </div>
      )}
    </Boundary>
  );
}
