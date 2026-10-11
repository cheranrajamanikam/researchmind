# ResearchMind

*A local-first research companion that shows the evidence and leaves the thinking to you.*

Upload research papers (PDFs), then search them, ask questions, compare their reported results and check your own
writing. Everything runs on your computer through [Ollama](https://ollama.com): no cloud keys, no per-question cost,
and your papers never leave the machine.

**The core rule:** the model never writes citations. It only says "I used excerpt 2"; the backend fills in the real
paper, page and verbatim quote from what it retrieved. If your papers don't contain the answer, the app says
*insufficient evidence* instead of guessing.

## Quick start

You need Python 3.11+, Node 20+ (only to build the interface once) and Ollama.

```bash
# 1. models (once)
ollama pull qwen2.5:7b          # answers and extraction
ollama pull nomic-embed-text    # embeddings for semantic search

# 2. backend dependencies
pip install -r backend/requirements.txt

# 3. run (builds the frontend on first start, then serves everything on one port)
python run.py
```

Open <http://127.0.0.1:8000>. On first launch you create a local password; that is the only account.

| Command | What it does |
|---|---|
| `python run.py` | Start API + interface on `127.0.0.1:8000` |
| `python run.py --check` | Diagnose Python, packages, Node, database, Ollama and installed models |
| `python run.py --test` | Run the backend tests (and frontend tests if `node_modules` exists) |
| `python run.py --rebuild` | Reinstall frontend packages and rebuild the interface |
| `python run.py --dev` | API with auto-reload plus the Vite dev server on `:5173` |

Different models? Change them in **Settings**, or set `RM_ANSWER_MODEL` / `RM_EMBED_MODEL` (copy `.env.example` to `.env`).

### Docker (optional, untested here)

```bash
docker compose up --build       # http://localhost:8000
```

Ollama stays on your machine; the container reaches it at `host.docker.internal`. On Linux start Ollama with
`OLLAMA_HOST=0.0.0.0`. **These Docker files were written but could not be built in the environment where this
project was assembled (no Docker daemon). Expect to fix small things on first build.**

## What's inside

| Area | Pages |
|---|---|
| Workspace | Overview dashboard, Papers, Add papers, Paper viewer (with page jump and highlighted quotes), Search, Projects |
| Questions | Threads (saved conversations), Copilot drawer with a *Reading mode* that points you to what to read instead of writing prose |
| Evaluate | Evaluation harness, Extraction review, Paper diff, Contradictions |
| Discover | Find references, Reading list, Search receipts, Prior-work audit, Gap map |
| Integrity | Numeric consistency, Reproducibility X-ray, Overclaim meter, Citation audit |
| Think first | Prediction gate, Decision log (with conflict alerts), Provenance log |

Design rules baked into every analysis page: an *Analytical estimate, not proof* label, a *How this was computed*
section, quotes with page numbers for every claim, and no verdicts (nothing is called "novel", "correct" or
"AI-written"; there is no novelty score and no AI-text detector).

## How it works

```
PDF ──► text per page ──► page-aware chunks ──► Ollama embeddings ──► SQLite (chunks + FTS5 keyword index)
                                   └─► table parsing (pdfplumber) + two-pass extraction ──► fields with page + quote

Question ──► keyword + semantic retrieval ──► numbered excerpts ──► Ollama ──► "sufficient?, answer, excerpts used"
         ──► backend checks the numbers, resolves them to real paper / page / quote ──► interface
         (no usable evidence, or the model refuses ──► "insufficient evidence", no citations shown)
```

```
frontend/  React 19 + Vite + Tailwind 4      pages/ components/ layout/ api/ (single API layer) lib/
backend/   FastAPI + SQLAlchemy + Alembic    app/api/ (routes) app/services/ (logic) eval/ tests/
run.py     launcher: run / --check / --test / --rebuild / --dev
data/      database, uploaded PDFs, generated secret key (git-ignored; delete it to start fresh)
```

API documentation is served at <http://127.0.0.1:8000/api/docs> while the app runs.

## Privacy

- Paper text is only ever sent to your own Ollama server.
- **Online discovery is off by default.** When you switch it on in Settings, only short search queries (≤100
  characters) go to OpenAlex, Semantic Scholar and arXiv, never paper content, and the interface changes to a
  distinct "Online discovery active" state. Every run saves a *search receipt* listing what was and wasn't searched.
- Fonts are bundled; the built interface makes no third-party requests.
- Settings → *Export all data* and *Delete all data* (typed confirmation) both work.

## What has and hasn't been verified

Verified in the environment where this was assembled:

- 55 backend tests and 24 frontend tests pass; TypeScript compiles with no errors; production build succeeds.
- An end-to-end run started the real app process with real PDFs and checked 37 behaviours: first-run setup, locked
  API, upload (including rejecting non-PDFs), processing, keyword and semantic search, cited answers whose quotes
  exist in the stored text, *insufficient evidence* on an unsupported question, graceful behaviour with Ollama
  offline, persistence across a restart, and paper/data deletion.
- The app starts with only `backend/requirements.txt` installed.

**Not verified:**

- **Answer and extraction quality with a real model.** The end-to-end run used a stand-in for Ollama. Small local
  models can give shallow answers; the citation checks stop invented sources but cannot make a model smarter.
  Run the evaluation (below) on your own papers before trusting any number.
- Docker build (see above), Windows/macOS, and a person clicking through the interface in a real browser.
- Visual match to the Figma frames was not measured.

## Evaluation

Evaluation → *Run evaluation* in the interface, or from the command line:

```bash
cd backend
python -m eval.cli --project 1 --load-samples        # bundled question set (needs its sample papers uploaded)
python -m eval.cli --project 1 --k 10 --judge        # optional local-LLM judge for citation faithfulness
```

It reports recall@k, MRR, citation faithfulness and whether the system correctly refuses unanswerable questions,
and writes JSON + Markdown reports. No benchmark numbers are claimed here because none were measured against a real
model.

## Known limitations

- **No OCR.** Scanned PDFs are detected and reported as having no text layer.
- **SQLite only.** The keyword index uses SQLite FTS5, so PostgreSQL is not supported.
- **Semantic search compares vectors in memory** (embeddings are stored in the database and survive restarts).
  That suits hundreds of papers, not tens of thousands.
- **Single user.** One local password, no accounts or sharing.
- **Result parsing is deliberately conservative.** Numeric consistency and contradictions only use results that
  name their method ("TransMed obtains 89.1% accuracy on ChestXray") or appear in a table. Vaguer sentences ("our
  method works well") are skipped, so expect missed findings rather than wrong ones.
- Contradictions and Paper diff depend on extraction, which depends on the model you run.
- Not built: knowledge graph, hypothesis generation, automated experiment design.

## Troubleshooting

- `python run.py --check` explains most problems (missing package, Ollama not running, model not pulled).
- *"Ollama is not reachable"*: start Ollama, then check the URL in Settings. Keyword search works without it.
- Forgot the password: stop the app and delete `data/researchmind.db` (this deletes your library) or the whole `data/` folder.
- Port busy: `python run.py --port 8001`.
