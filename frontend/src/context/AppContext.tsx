import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api, getToken, setToken, UNAUTHORIZED_EVENT } from "@/api/client";
import type { AppSettings, OllamaStatus, Paper, Project } from "@/api/types";
import { usePolling } from "@/api/hooks";

type AuthPhase = "loading" | "unreachable" | "setup" | "login" | "ready";
export interface Toast { id: number; message: string; kind: "ok" | "error" }

interface Ctx {
  phase: AuthPhase;
  userName: string;
  signIn: (password: string) => Promise<void>;
  setup: (name: string, password: string) => Promise<void>;
  signOut: () => void;
  retryBoot: () => void;

  projects: Project[];
  project: Project | null;
  projectId: number | null;
  selectProject: (id: number) => void;
  refreshProjects: () => Promise<Project[]>;

  settings: AppSettings | null;
  saveSettings: (patch: Partial<AppSettings>) => Promise<AppSettings>;
  ollama: OllamaStatus | null;
  refreshOllama: () => Promise<OllamaStatus | null>;

  jobs: Paper[];
  activeJobs: number;
  refreshJobs: () => void;

  dark: boolean;
  toggleTheme: () => void;

  toasts: Toast[];
  toast: (message: string, kind?: Toast["kind"]) => void;

  copilotOpen: boolean;
  setCopilotOpen: (v: boolean) => void;
  evidenceOpen: boolean;
  setEvidenceOpen: (v: boolean) => void;
}

const AppCtx = createContext<Ctx | null>(null);
const PROJECT_KEY = "rm_project";
const THEME_KEY = "rm_theme";

function readStore(key: string): string | null {
  try { return localStorage.getItem(key); } catch { return null; }
}
function writeStore(key: string, value: string): void {
  try { localStorage.setItem(key, value); } catch { /* per-viewer convenience only */ }
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [phase, setPhase] = useState<AuthPhase>("loading");
  const [userName, setUserName] = useState("");
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState<number | null>(() => {
    const v = readStore(PROJECT_KEY);
    return v ? Number(v) : null;
  });
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [ollama, setOllama] = useState<OllamaStatus | null>(null);
  const [jobs, setJobs] = useState<Paper[]>([]);
  const [dark, setDark] = useState<boolean>(() => {
    const v = readStore(THEME_KEY);
    if (v) return v === "dark";
    return typeof window !== "undefined" && window.matchMedia?.("(prefers-color-scheme: dark)").matches === true;
  });
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [copilotOpen, setCopilotOpen] = useState(false);
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const toastId = useRef(0);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    document.documentElement.style.colorScheme = dark ? "dark" : "light";
  }, [dark]);

  const toggleTheme = useCallback(() => {
    setDark((d) => { writeStore(THEME_KEY, d ? "light" : "dark"); return !d; });
  }, []);

  const toast = useCallback((message: string, kind: Toast["kind"] = "ok") => {
    const id = ++toastId.current;
    setToasts((t) => [...t, { id, message, kind }]);
    window.setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), kind === "error" ? 7000 : 3800);
  }, []);

  const refreshProjects = useCallback(async () => {
    const rows = await api.get<Project[]>("/projects");
    setProjects(rows);
    setProjectId((cur) => {
      const next = cur && rows.some((p) => p.id === cur) ? cur : rows[0]?.id ?? null;
      if (next) writeStore(PROJECT_KEY, String(next));
      return next;
    });
    return rows;
  }, []);

  const refreshOllama = useCallback(async () => {
    try {
      const s = await api.get<OllamaStatus>("/system/ollama");
      setOllama(s);
      return s;
    } catch {
      return null;
    }
  }, []);

  const loadWorkspace = useCallback(async () => {
    const [, s] = await Promise.all([refreshProjects(), api.get<AppSettings>("/settings")]);
    setSettings(s);
    void refreshOllama();
  }, [refreshProjects, refreshOllama]);

  const boot = useCallback(async () => {
    setPhase("loading");
    try {
      const st = await api.get<{ setup_required: boolean; user_name: string | null }>("/auth/status");
      if (st.setup_required) { setPhase("setup"); return; }
      setUserName(st.user_name ?? "");
      if (!getToken()) { setPhase("login"); return; }
      try {
        const me = await api.get<{ name: string }>("/auth/me");
        setUserName(me.name);
        await loadWorkspace();
        setPhase("ready");
      } catch {
        setToken(null);
        setPhase("login");
      }
    } catch {
      setPhase("unreachable");
    }
  }, [loadWorkspace]);

  useEffect(() => { void boot(); }, [boot]);

  useEffect(() => {
    const onUnauthorized = () => setPhase("login");
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    return () => window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
  }, []);

  const finishAuth = useCallback(async (res: { token: string; user: { name: string } }) => {
    setToken(res.token);
    setUserName(res.user.name);
    await loadWorkspace();
    setPhase("ready");
  }, [loadWorkspace]);

  const signIn = useCallback(async (password: string) => {
    await finishAuth(await api.post("/auth/login", { password }));
  }, [finishAuth]);
  const setup = useCallback(async (name: string, password: string) => {
    await finishAuth(await api.post("/auth/setup", { name, password }));
  }, [finishAuth]);
  const signOut = useCallback(() => {
    setToken(null);
    setProjects([]);
    setSettings(null);
    setPhase("login");
  }, []);

  const saveSettings = useCallback(async (patch: Partial<AppSettings>) => {
    const next = await api.put<AppSettings>("/settings", patch);
    setSettings(next);
    if ("ollama_url" in patch || "answer_model" in patch || "embed_model" in patch) void refreshOllama();
    return next;
  }, [refreshOllama]);

  const selectProject = useCallback((id: number) => {
    writeStore(PROJECT_KEY, String(id));
    setProjectId(id);
  }, []);

  const refreshJobs = useCallback(() => {
    if (!projectId) { setJobs([]); return; }
    api.get<Paper[]>(`/jobs?project_id=${projectId}`).then(setJobs).catch(() => undefined);
  }, [projectId]);

  useEffect(() => { if (phase === "ready") refreshJobs(); }, [phase, refreshJobs]);
  const activeJobs = jobs.filter((j) => j.job_state === "queued" || j.job_state === "running").length;
  usePolling(refreshJobs, 2500, phase === "ready" && activeJobs > 0);
  usePolling(refreshJobs, 15000, phase === "ready" && activeJobs === 0);

  const project = useMemo(() => projects.find((p) => p.id === projectId) ?? null, [projects, projectId]);

  const value: Ctx = {
    phase, userName, signIn, setup, signOut, retryBoot: () => void boot(),
    projects, project, projectId, selectProject, refreshProjects,
    settings, saveSettings, ollama, refreshOllama,
    jobs, activeJobs, refreshJobs,
    dark, toggleTheme, toasts, toast,
    copilotOpen, setCopilotOpen, evidenceOpen, setEvidenceOpen,
  };
  return <AppCtx.Provider value={value}>{children}</AppCtx.Provider>;
}

export function useApp(): Ctx {
  const c = useContext(AppCtx);
  if (!c) throw new Error("useApp must be used inside <AppProvider>");
  return c;
}

/** Pages that need a project call this; the shell guarantees one exists once the user is signed in. */
export function useProjectId(): number {
  const { projectId } = useApp();
  return projectId ?? 0;
}
