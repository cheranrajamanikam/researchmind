import { useEffect, useRef, useState } from "react";
import { api, setToken } from "@/api/client";
import { useAction } from "@/api/hooks";
import type { OllamaStatus } from "@/api/types";
import { Icon } from "@/components/Icon";
import { Button, Modal, PageTitle, Pill, Switch } from "@/components/ui";
import { useApp } from "@/context/AppContext";

const SECTIONS = [["models", "AI & models"], ["privacy", "Privacy"], ["analysis", "Analysis"], ["appearance", "Appearance"], ["data", "Data & export"]] as const;

export default function Settings() {
  const { settings, saveSettings, ollama, refreshOllama, dark, toggleTheme, toast } = useApp();
  const [url, setUrl] = useState(settings?.ollama_url ?? "");
  const [answer, setAnswer] = useState(settings?.answer_model ?? "");
  const [embed, setEmbed] = useState(settings?.embed_model ?? "");
  const [tolerance, setTolerance] = useState(settings?.tolerance ?? 5);
  const [tested, setTested] = useState<OllamaStatus | null>(null);
  const [active, setActive] = useState<string>("models");
  const [deleting, setDeleting] = useState(false);
  const [typed, setTyped] = useState("");
  const timer = useRef<number | undefined>(undefined);

  useEffect(() => {
    if (!settings) return;
    setUrl(settings.ollama_url); setAnswer(settings.answer_model); setEmbed(settings.embed_model); setTolerance(settings.tolerance);
  }, [settings]);
  useEffect(() => { void refreshOllama(); }, [refreshOllama]);

  const test = useAction(async () => setTested(await api.post<OllamaStatus>("/system/ollama/test", { url: url.trim() })));
  const saveModels = useAction(async () => {
    await saveSettings({ ollama_url: url.trim(), answer_model: answer, embed_model: embed });
    toast("Model settings saved");
  });
  const flip = useAction(async (patch: Parameters<typeof saveSettings>[0]) => { await saveSettings(patch); toast("Saved"); });
  const exportAll = useAction(async () => { await api.download("/data/export", "researchmind-export.zip", "POST"); toast("Export created"); });
  const wipe = useAction(async () => {
    await api.del("/data", { confirm: "DELETE" });
    setToken(null);
    window.location.assign("/");
  });

  const onTolerance = (v: number) => {
    setTolerance(v);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => void saveSettings({ tolerance: v }).catch(() => toast("Could not save tolerance", "error")), 450);
  };

  if (!settings) return null;
  const status = tested ?? ollama;
  const models = status?.models ?? [];
  const options = (cur: string) => (cur && !models.includes(cur) ? [cur, ...models] : models);
  const dirty = url.trim() !== settings.ollama_url || answer !== settings.answer_model || embed !== settings.embed_model;
  const go = (id: string) => { setActive(id); document.getElementById(`s-${id}`)?.scrollIntoView({ behavior: "smooth", block: "start" }); };

  return (
    <div className="screen">
      <PageTitle title="Settings" description="Manage local models, privacy, analysis behavior, and your data." />
      <div className="settings-layout">
        <aside>{SECTIONS.map(([id, label]) => <button key={id} className={active === id ? "active" : ""} onClick={() => go(id)}>{label}</button>)}</aside>
        <main>
          <section className="settings-section" id="s-models">
            <div className="settings-heading">
              <div><h2>Local AI connection</h2><p>ResearchMind uses Ollama to run models on this machine.</p></div>
              {status && <Pill tone={status.reachable ? "teal" : "amber"}><i className="status-dot" /> {status.reachable ? "Connected" : "Not reachable"}</Pill>}
            </div>
            <label>Ollama URL
              <div className="input-action">
                <input value={url} onChange={(e) => { setUrl(e.target.value); setTested(null); }} inputMode="url" spellCheck={false} />
                <Button onClick={() => void test.run()} disabled={test.busy || !url.trim()}>{test.busy ? "Testing…" : "Test connection"}</Button>
              </div>
              <small>{status ? (status.reachable ? `Connected · Ollama ${status.version} · ${status.models.length} models installed` : status.error || "Could not reach Ollama at this address.") : "Checking…"}</small>
            </label>
            <div className="two-col">
              <label>Answer model
                <select value={answer} onChange={(e) => setAnswer(e.target.value)}>{options(answer).map((m) => <option key={m} value={m}>{m}{models.includes(m) ? "" : " (not installed)"}</option>)}</select>
              </label>
              <label>Embedding model
                <select value={embed} onChange={(e) => setEmbed(e.target.value)}>{options(embed).map((m) => <option key={m} value={m}>{m}{models.includes(m) ? "" : " (not installed)"}</option>)}</select>
              </label>
            </div>
            {status?.reachable && (!status.answer_model_installed || !status.embed_model_installed) && !dirty && (
              <p className="form-error" style={{ color: "var(--amber)" }}>Missing model: run <code>ollama pull {!status.answer_model_installed ? status.answer_model : status.embed_model}</code>.</p>
            )}
            <small className="muted">Changing the embedding model means existing papers should be re-indexed from the Papers page so search stays consistent.</small>
            {saveModels.error && <p className="form-error" role="alert">{saveModels.error}</p>}
            <div><Button variant="primary" onClick={() => void saveModels.run()} disabled={!dirty || saveModels.busy}>Save model settings</Button></div>
          </section>

          <section className="settings-section" id="s-privacy">
            <div className="settings-heading">
              <div><h2>Online discovery</h2><p>Search external scholarly indexes for papers not in your library.</p></div>
              <Switch checked={settings.online_discovery} onChange={(v) => void flip.run({ online_discovery: v })} label="Online discovery" disabled={flip.busy} />
            </div>
            <div className={`online-explainer ${settings.online_discovery ? "active" : ""}`}>
              <Icon name={settings.online_discovery ? "wifi" : "archive"} />
              <div>
                <b>{settings.online_discovery ? "Online discovery is active" : "Local mode only"}</b>
                <p>{settings.online_discovery
                  ? "Only short search queries (you see them before and after each search) may be sent to OpenAlex, Semantic Scholar and arXiv. Paper files, extracted text, notes and embeddings never leave this device."
                  : "Searches use only your local library. No queries, papers, notes, or embeddings leave this device."}</p>
              </div>
            </div>
          </section>

          <section className="settings-section" id="s-analysis">
            <div className="settings-heading"><div><h2>Analysis defaults</h2><p>Choose how ResearchMind supports your reading process.</p></div></div>
            <div className="setting-row">
              <div><b>Think-first by default</b><p>New projects ask for your prediction before revealing extracted comparisons.</p></div>
              <Switch checked={settings.think_first_default} onChange={(v) => void flip.run({ think_first_default: v })} label="Think-first by default" />
            </div>
            <label>Numeric comparison tolerance
              <div className="range-row"><input type="range" min={0} max={20} value={tolerance} onChange={(e) => onTolerance(Number(e.target.value))} aria-label="Numeric comparison tolerance" /><b>{tolerance}%</b></div>
              <small>Values within this range are treated as approximately equivalent, not identical. Used by the Contradictions view.</small>
            </label>
          </section>

          <section className="settings-section" id="s-appearance">
            <div className="settings-heading"><div><h2>Appearance</h2><p>The theme is remembered on this device.</p></div></div>
            <div className="setting-row"><div><b>Dark theme</b><p>Easier on the eyes in low light.</p></div><Switch checked={dark} onChange={toggleTheme} label="Dark theme" /></div>
          </section>

          <section className="settings-section" id="s-data">
            <div className="settings-heading"><div><h2>Your data</h2><p>Export a portable archive or permanently remove local data.</p></div></div>
            <div className="setting-row"><div><b>Export all data</b><p>Papers, extracted fields, projects, threads, decisions and provenance logs as a zip.</p></div>
              <Button icon="download" onClick={() => void exportAll.run()} disabled={exportAll.busy}>{exportAll.busy ? "Creating…" : "Create export"}</Button></div>
            {exportAll.error && <p className="form-error" role="alert">{exportAll.error}</p>}
            <div className="setting-row"><div><b>Delete all data</b><p>This permanently removes ResearchMind data from this device, including your account and every PDF.</p></div>
              <Button variant="danger" onClick={() => { setTyped(""); setDeleting(true); }}>Delete data…</Button></div>
          </section>
        </main>
      </div>

      {deleting && (
        <Modal title="Delete all ResearchMind data?" onClose={() => setDeleting(false)}
          actions={<><Button onClick={() => setDeleting(false)}>Cancel</Button><Button variant="danger" disabled={typed !== "DELETE" || wipe.busy} onClick={() => void wipe.run()}>{wipe.busy ? "Deleting…" : "Delete everything"}</Button></>}>
          <p>Every project, paper, thread, decision and note will be erased, along with the stored PDFs and your account. <b>This cannot be undone.</b> Consider creating an export first.</p>
          <label>Type <b>DELETE</b> to confirm<input value={typed} onChange={(e) => setTyped(e.target.value)} autoFocus autoComplete="off" /></label>
          {wipe.error && <p className="form-error" role="alert">{wipe.error}</p>}
        </Modal>
      )}
    </div>
  );
}
