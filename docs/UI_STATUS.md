# UI status: every screen of the design, and what backs it

Source design: `design/ResearchMind_UI_Design_System.zip` (Figma Make export). The tokens (`:root` and `.dark`
CSS variables), component names and class names were kept; the single 78 KB `App.tsx` was split into
`components/`, `layout/` and `pages/`, and the `useState` page switch was replaced by real routes.

**No screen uses mock data.** All 26 design screens read and write through the API layer
(`frontend/src/api/`). "Verified" below means exercised by the automated end-to-end run
(real PDFs, fake Ollama, real server process) or by the backend test suite.

| Design screen | Route | Backing endpoints | Verified by |
|---|---|---|---|
| Login / first-run setup | `/` (shown until signed in) | `/api/auth/status`, `/auth/setup`, `/auth/login` | e2e |
| Overview | `/` | `/api/projects/{id}/overview`, `/jobs` | e2e |
| Papers library | `/papers` | `/api/papers`, `DELETE /papers/{id}` | e2e |
| Upload | `/upload` | `POST /api/projects/{id}/papers`, `/jobs`, `/papers/{id}/retry` | e2e |
| Paper viewer | `/papers/:id` | `/api/papers/{id}`, `/pages`, `/file`, `/fields` | e2e |
| Search | `/search` | `POST /api/search` (keyword / semantic) | e2e |
| Projects, project detail | `/projects`, `/projects/:id` | `/api/projects` | tests |
| Threads, thread detail | `/threads`, `/threads/:id` | `/api/threads`, `/threads/{id}/messages` | e2e |
| Copilot drawer | any page | `POST /api/copilot/ask` | e2e |
| Settings | `/settings` | `/api/settings`, `/system/ollama`, `POST /data/export`, `DELETE /data` | e2e |
| Evaluation | `/evaluation` | `/api/projects/{id}/eval/*` | tests + e2e |
| Find references | `/references` | `POST /api/projects/{id}/discover` | tests (mocked network) |
| Reading list | `/reading` | `/api/projects/{id}/reading`, `/reading/{id}` | tests |
| Search receipts | `/receipts`, `/receipts/:id` | `/api/projects/{id}/receipts`, `/receipts/{id}` | tests |
| Extraction review | `/extraction` | `/api/projects/{id}/extraction`, `PATCH /fields/{id}` | tests |
| Paper diff | `/diff` | `POST /api/projects/{id}/diff` | tests |
| Contradictions | `/contradictions` | `/api/projects/{id}/contradictions` | tests (synthetic conflicts) |
| Numeric consistency | `/numeric` | `/api/papers/{id}/numeric` | tests |
| Reproducibility X-ray | `/reproducibility` | `/api/papers/{id}/reproducibility` | tests |
| Overclaim meter | `/overclaim` | `POST /api/projects/{id}/overclaim` | tests |
| Citation audit | `/audit` | `/api/projects/{id}/citation-audit` | tests |
| Prior-work audit | `/prior-work` | `POST /api/projects/{id}/prior-work` | tests |
| Gap map | `/gaps` | `/api/projects/{id}/gaps` | tests |
| Prediction gate | `/prediction` | `/api/projects/{id}/predictions` | tests |
| Decision log | `/decisions` | `/api/projects/{id}/decisions`, `/alerts/{id}/resolve` | tests |
| Provenance log | `/provenance` | `/api/projects/{id}/provenance`, `/provenance/{id}/export.*` | tests |

## Deliberate deviations from the design

- **Fonts are bundled** (`@fontsource-variable/inter`, `@fontsource-variable/source-serif-4`). The design loaded
  them from Google Fonts, which would send a request off the machine on every page load. The production build
  makes no third-party requests.
- **Red is for system problems only** (failed job, Ollama offline, delete confirmation). It never means
  "wrong"; amber means "needs your review".
- **Figma artifacts removed:** the `.figma/` folder, Figma Make Vite plugins and the "Preview first-run setup"
  button. First-run setup is a real route driven by backend state.
- **Added on top of the design** (same tokens and radii): loading skeletons, error states, an "Ollama offline"
  state, the calm "Insufficient evidence" state, and keyboard/aria improvements.

## Not verified here

- Visual pixel-comparison against the Figma frames was not done. The layout follows the exported code, not the
  rendered Figma canvas.
- Screens were exercised through the API and component smoke tests (24 frontend tests), not by a person
  clicking through a real browser against a real Ollama model.
