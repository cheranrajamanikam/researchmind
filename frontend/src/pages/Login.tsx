import { useState, type FormEvent } from "react";
import { api, setToken } from "@/api/client";
import type { AppSettings, OllamaStatus } from "@/api/types";
import { useAction } from "@/api/hooks";
import { Icon } from "@/components/Icon";
import { ErrorState } from "@/components/states";
import { Button } from "@/components/ui";
import { useApp } from "@/context/AppContext";

function Visual() {
  return (
    <>
      <div className="login__brand"><div className="brand-mark">R</div><span>ResearchMind</span></div>
      <div className="login__visual">
        <div className="quote-visual">
          <span>Evidence in view</span>
          <blockquote>“The strongest research tools make uncertainty visible, and keep the source within reach.”</blockquote>
          <div><i /><small>Your library stays on this machine.</small></div>
        </div>
        <p>A local-first research companion that shows the evidence and leaves the thinking to you.</p>
      </div>
    </>
  );
}

/** Returning user: unlock the local workspace. */
export function SignIn() {
  const { signIn, userName } = useApp();
  const [password, setPassword] = useState("");
  const act = useAction(signIn);
  const submit = async (e: FormEvent) => { e.preventDefault(); await act.run(password); };
  return (
    <div className="login">
      <Visual />
      <main className="login__card">
        <form onSubmit={submit} className="stack-form" style={{ display: "contents" }}>
          <h1>{userName ? `Welcome back, ${userName.split(" ")[0]}` : "Welcome back"}</h1>
          <p>Enter the password for this device to open your workspace.</p>
          <label>Local password
            <input type="password" autoFocus autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} />
          </label>
          {act.error && <p className="form-error" role="alert">{act.error}</p>}
          <Button variant="primary" type="submit" disabled={act.busy || !password}>Open ResearchMind <Icon name="arrow" size={15} /></Button>
          <small className="login-note"><Icon name="archive" size={14} /> The password is checked on this device only.</small>
        </form>
      </main>
    </div>
  );
}

/** First run: create the local user, then check Ollama and choose models. */
export function FirstRun() {
  const { retryBoot } = useApp();
  const [step, setStep] = useState<0 | 1>(0);
  const [name, setName] = useState("");
  const [pw, setPw] = useState("");
  const [pw2, setPw2] = useState("");
  const [local, setLocal] = useState<string | null>(null);
  const [ollama, setOllama] = useState<OllamaStatus | null>(null);
  const [answer, setAnswer] = useState("");
  const [embed, setEmbed] = useState("");

  const create = useAction(async () => {
    const res = await api.post<{ token: string }>("/auth/setup", { name: name.trim(), password: pw });
    setToken(res.token);
    const [o, s] = await Promise.all([api.get<OllamaStatus>("/system/ollama"), api.get<AppSettings>("/settings")]);
    setOllama(o);
    setAnswer(s.answer_model);
    setEmbed(s.embed_model);
    setStep(1);
  });

  const finish = useAction(async () => {
    await api.put("/settings", { answer_model: answer, embed_model: embed });
    retryBoot();
  });

  const next = async (e: FormEvent) => {
    e.preventDefault();
    setLocal(null);
    if (!name.trim()) return setLocal("Enter your name.");
    if (pw.length < 8) return setLocal("Use at least 8 characters.");
    if (pw !== pw2) return setLocal("The two passwords don't match.");
    await create.run();
  };

  const models = ollama?.models ?? [];
  const withCurrent = (cur: string) => (models.includes(cur) || !cur ? models : [cur, ...models]);

  return (
    <div className="login">
      <Visual />
      <main className="login__card">
        {step === 0 ? (
          <form onSubmit={next} style={{ display: "contents" }}>
            <div className="step-count">STEP 1 OF 2</div>
            <h1>Create your local workspace</h1>
            <p>Set a password for this device. No account or internet connection is required.</p>
            <label>Your name<input value={name} onChange={(e) => setName(e.target.value)} autoFocus autoComplete="name" /></label>
            <label>Local password<input type="password" value={pw} onChange={(e) => setPw(e.target.value)} autoComplete="new-password" /></label>
            <label>Confirm password<input type="password" value={pw2} onChange={(e) => setPw2(e.target.value)} autoComplete="new-password" /></label>
            {(local || create.error) && <p className="form-error" role="alert">{local ?? create.error}</p>}
            <Button variant="primary" type="submit" disabled={create.busy}>Continue <Icon name="arrow" size={15} /></Button>
            <small className="login-note"><Icon name="archive" size={14} /> Your password is hashed and stored on this device. It cannot be recovered remotely.</small>
          </form>
        ) : (
          <>
            <div className="step-count">STEP 2 OF 2</div>
            <h1>Connect local AI</h1>
            <p>ResearchMind uses Ollama for private, on-device analysis.</p>
            {ollama?.reachable ? (
              <div className="connection-ok"><Icon name="check" /><div><b>Ollama is ready</b><span>{ollama.url} · version {ollama.version}</span></div></div>
            ) : (
              <div className="banner banner--offline" role="alert"><Icon name="wifi" size={18} />
                <div><b>Ollama isn't running</b><p>You can continue now: keyword search and uploads work. Start Ollama (<code>ollama serve</code>) and pull the models later for semantic search and answers.</p></div>
              </div>
            )}
            <label>Answer model
              <select value={answer} onChange={(e) => setAnswer(e.target.value)}>
                {withCurrent(answer).map((m) => <option key={m} value={m}>{m}{m === answer && !models.includes(m) ? " (not installed)" : ""}</option>)}
                {!answer && <option value="">Choose a model</option>}
              </select>
            </label>
            <label>Embedding model
              <select value={embed} onChange={(e) => setEmbed(e.target.value)}>
                {withCurrent(embed).map((m) => <option key={m} value={m}>{m}{m === embed && !models.includes(m) ? " (not installed)" : ""}</option>)}
              </select>
            </label>
            {ollama?.reachable && (!ollama.answer_model_installed || !ollama.embed_model_installed) && (
              <p className="form-error" style={{ color: "var(--amber)" }}>
                Install the missing model with <code>ollama pull {!ollama.embed_model_installed ? ollama.embed_model : ollama.answer_model}</code>.
              </p>
            )}
            {finish.error && <p className="form-error" role="alert">{finish.error}</p>}
            <Button variant="primary" onClick={() => void finish.run()} disabled={finish.busy}>Open ResearchMind <Icon name="arrow" size={15} /></Button>
          </>
        )}
      </main>
    </div>
  );
}

export function Unreachable() {
  const { retryBoot } = useApp();
  return <ErrorState status={0} message="The ResearchMind server isn't responding. Start it with `python run.py`, then try again." onRetry={retryBoot} />;
}
