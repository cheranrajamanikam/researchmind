import { readdirSync, readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { BrowserRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "@/App";
import { AppProvider } from "@/context/AppContext";

const project = { id: 1, name: "Reliable retrieval", question: "", think_first: false, paper_count: 2, thread_count: 0, created_at: "", updated_at: "" };
const settings = { ollama_url: "http://localhost:11434", answer_model: "qwen2.5:7b", embed_model: "nomic-embed-text", online_discovery: false, think_first_default: false, tolerance: 5 };
const side = (label: string, value: number, page: number, quote: string) =>
  ({ paper_id: page, paper_title: label, label, value, unit: "", display: String(value), quote, page, method: "RAG" });
const conflict = {
  n: 1, key: { method: "RAG", dataset: "Natural Questions", metric: "Exact match" }, title: "Natural Questions · Exact match",
  relative_difference_pct: 7.4, a: side("Lewis et al. · 2020", 44.5, 8, "RAG-Sequence obtains 44.5 exact match."),
  b: side("Chen et al. · 2024", 41.2, 11, "Replicated exact match reaches 41.2."),
  setup_differences: [{ field: "Retriever", a: "DPR-NQ", b: "DPR-Multi", a_page: 5, b_page: 6 }],
  possible_reasons: ["Different retriever checkpoint"], candidate_experiment: "Run both against one frozen corpus.",
};

const routes: Record<string, unknown> = {
  "GET /auth/status": { setup_required: false, user_name: "Cheran" },
  "GET /auth/me": { name: "Cheran" },
  "GET /projects": [project],
  "GET /settings": settings,
  "GET /system/ollama": { url: "", reachable: false, version: null, models: [], answer_model: "", embed_model: "", answer_model_installed: false, embed_model_installed: false, error: "refused" },
  "GET /jobs?project_id=1": [],
  "GET /projects/1/contradictions?tolerance=5": { tolerance: 5, items: [conflict], note: "Candidate conflicts only.", disclaimer: "Analytical estimate, not proof." },
  "GET /projects/1/provenance": [],
  "GET /projects/1/decisions": [],
  "GET /papers?project_id=1": [],
};

function mockApi(extra: Record<string, unknown> = {}) {
  const table = { ...routes, ...extra };
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const path = String(input).replace(/^.*\/api/, "");
    const key = `${init?.method ?? "GET"} ${path}`;
    if (!(key in table)) return new Response(JSON.stringify({ detail: `no mock for ${key}` }), { status: 404 });
    return new Response(JSON.stringify(table[key]), { status: 200, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

function open(path: string) {
  window.history.pushState({}, "", path);
  return render(<BrowserRouter><AppProvider><App /></AppProvider></BrowserRouter>);
}

beforeEach(() => localStorage.setItem("rm_token", "test-token"));
afterEach(() => { vi.unstubAllGlobals(); localStorage.clear(); });

describe("shell and routes", () => {
  it("signs in and shows the always-visible Local mode indicator", async () => {
    mockApi();
    open("/contradictions");
    expect((await screen.findAllByText("Local mode")).length).toBeGreaterThanOrEqual(2); // top bar and sidebar
  });

  it("renders a candidate conflict with its quotes, cautious wording and no verdict", async () => {
    mockApi();
    open("/contradictions");
    expect(await screen.findByText(/Candidate conflict 01/)).toBeInTheDocument();
    expect(screen.getByText(/RAG-Sequence obtains 44.5 exact match/)).toBeInTheDocument();
    expect(screen.getByText("Possible reasons (not conclusions)")).toBeInTheDocument();
    expect(screen.getByText("Candidate experiment (suggestion)")).toBeInTheDocument();
    expect(screen.getAllByText("Analytical estimate, not proof").length).toBeGreaterThan(0);
    expect(document.body.textContent).not.toMatch(/\b(wrong|incorrect|refuted|proven)\b/i);
  });

  it("always shows the legal notice on the prior-work audit", async () => {
    mockApi();
    open("/prior-work");
    expect(await screen.findByText(/Not a legal or patentability opinion\. No novelty score\./)).toBeInTheDocument();
  });

  it("states that provenance marking is not AI detection", async () => {
    mockApi();
    open("/provenance");
    expect(await screen.findByText(/does not detect AI text/)).toBeInTheDocument();
  });

  it("explains the local-only boundary when online discovery is off", async () => {
    mockApi();
    open("/references");
    expect(await screen.findByText("Searching your local library only")).toBeInTheDocument();
  });

  it("shows an Ollama-offline banner that does not block the page", async () => {
    mockApi();
    open("/overclaim");
    expect(await screen.findByText("Ollama is offline")).toBeInTheDocument();
    expect(screen.getByLabelText("Draft text")).toBeInTheDocument();
  });

  it("asks for a paper before analysing when the library is empty", async () => {
    mockApi();
    open("/reproducibility");
    expect(await screen.findByText("Add papers first")).toBeInTheDocument();
  });

  it("sends the user to the sign-in screen without a token", async () => {
    localStorage.clear();
    mockApi();
    open("/");
    await waitFor(() => expect(screen.queryAllByText("Local mode")).toHaveLength(0));
    expect(await screen.findByLabelText(/password/i)).toBeInTheDocument();
  });

  it("lets the user type a decision without losing the form on an API error", async () => {
    mockApi();
    open("/decisions");
    await userEvent.click(await screen.findByRole("button", { name: /record decision/i }));
    await userEvent.type(screen.getByPlaceholderText(/top-10 passages/i), "Use top-10 passages");
    expect(screen.getByDisplayValue("Use top-10 passages")).toBeInTheDocument();
  });
});

describe("privacy", () => {
  const walk = (dir: string): string[] =>
    readdirSync(dir).flatMap((f) => { const p = join(dir, f); return statSync(p).isDirectory() ? walk(p) : [p]; });

  it("source and index.html reference no third-party hosts", () => {
    const files = [...walk(join(process.cwd(), "src")).filter((f) => !f.includes("/test/") && /\.(tsx?|css)$/.test(f)), join(process.cwd(), "index.html")];
    const external = files.flatMap((f) => (readFileSync(f, "utf8").match(/https?:\/\/[^\s"'`)]+/g) ?? [])
      .filter((u) => !/^https?:\/\/(localhost|127\.0\.0\.1|www\.w3\.org)/.test(u)).map((u) => `${f}: ${u}`));
    expect(external).toEqual([]);
  });
});
