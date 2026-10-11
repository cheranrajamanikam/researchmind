"""Command-line evaluation: runs the gold-question suite against a project and writes JSON + Markdown reports.

    cd backend
    python -m eval.cli --project 1 --load-samples            # bundled suite (needs the 4 sample papers uploaded)
    python -m eval.cli --project 1 --k 10 --judge            # optional LLM judge for citation faithfulness
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402
from app.db import SessionLocal, init_engine  # noqa: E402
from app.migrate import upgrade_to_head  # noqa: E402
from app.models import Project  # noqa: E402
from app.services import evaluation  # noqa: E402
from app.services.llm import get_llm  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Run the ResearchMind evaluation suite.")
    ap.add_argument("--project", type=int, required=True, help="project id")
    ap.add_argument("--k", type=int, default=10, help="recall@k cutoff")
    ap.add_argument("--judge", action="store_true", help="use the local LLM to judge citation faithfulness")
    ap.add_argument("--load-samples", action="store_true", help="replace gold questions with the bundled sample suite")
    ap.add_argument("--out", type=Path, default=None, help="report directory (default: <data>/eval_reports)")
    args = ap.parse_args(argv)

    cfg = get_settings()
    init_engine()
    upgrade_to_head(cfg.db_url)
    db = SessionLocal()
    try:
        if not db.get(Project, args.project):
            print(f"No project with id {args.project}.", file=sys.stderr)
            return 2
        if args.load_samples:
            n = evaluation.load_sample_suite(db, args.project)
            print(f"Loaded {n} sample questions.")
            if n == 0:
                print("None of the sample papers are in this project. Run `python -m eval.samples ./sample_papers` and upload them.", file=sys.stderr)
                return 2
        run = evaluation.run_out(evaluation.run_eval(db, args.project, get_llm(db), args.k, args.judge))
    finally:
        db.close()

    out = args.out or (cfg.data_dir / "eval_reports")
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    (out / f"eval-{stamp}.json").write_text(json.dumps(run, indent=2, ensure_ascii=False))
    (out / f"eval-{stamp}.md").write_text(evaluation.to_markdown(run))
    m = run["metrics"]
    print(f"Wrote {out / f'eval-{stamp}.json'} and .md")
    print(f"recall@{m['k']}={m['recall_at_k']}  MRR={m['mrr']}  faithfulness={m['citation_faithfulness']}  refusal={m['refusal_accuracy']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
