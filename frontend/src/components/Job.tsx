import type { Paper } from "@/api/types";
import { Icon } from "./Icon";
import { IconButton } from "./ui";

type Status = "running" | "done" | "queued" | "failed";

export function ProgressJob({
  title, detail, progress, status = "running", onRetry,
}: { title: string; detail: string; progress: number; status?: Status; onRetry?: () => void }) {
  const label = status === "running" ? `${Math.round(progress)}%` : status;
  return (
    <div className="job">
      <div className={`job__icon job__icon--${status}`}>
        {status === "done" ? <Icon name="check" /> : status === "queued" ? <Icon name="clock" /> : status === "failed" ? <Icon name="close" /> : <span className="spinner" />}
      </div>
      <div className="job__main">
        <div className="job__title"><b>{title}</b><span>{label}</span></div>
        <span>{detail}</span>
        <div className="progress" role="progressbar" aria-valuenow={Math.round(progress)} aria-valuemin={0} aria-valuemax={100} aria-label={`${title} progress`}>
          <i style={{ width: `${Math.max(0, Math.min(100, progress))}%` }} />
        </div>
      </div>
      {status === "failed" && onRetry ? <IconButton icon="arrow" label="Retry processing" onClick={onRetry} /> : <span style={{ width: 34 }} />}
    </div>
  );
}

export function PaperJob({ paper, onRetry }: { paper: Paper; onRetry?: (id: number) => void }) {
  const status: Status = paper.job_state;
  const detail = status === "failed" ? paper.error || "Processing failed" : paper.detail || paper.stage;
  return (
    <ProgressJob
      title={paper.title}
      detail={detail}
      progress={status === "done" ? 100 : paper.progress}
      status={status}
      onRetry={onRetry ? () => onRetry(paper.id) : undefined}
    />
  );
}
