import type { ReactNode } from "react";
import type { FieldStatus } from "@/api/types";
import { FIELD_STATUS_LABEL } from "@/lib/format";
import { useApp } from "@/context/AppContext";
import { Icon } from "./Icon";
import { PageTitle, Pill } from "./ui";

export function Disclaimer({ text = "Analytical estimate, not proof" }: { text?: string }) {
  return (
    <span className="disclaimer" title="Generated analyses can be incomplete. Review the cited source before relying on this result.">
      <Icon name="help" size={13} />{text}
    </span>
  );
}

export interface ComputedRow { label: string; value: string }

/** "How this was computed": real models, settings and timestamps, never placeholder text. */
export function HowComputed({
  label = "How this was computed", rows = [], completedAt,
}: { label?: string; rows?: ComputedRow[]; completedAt?: string | Date | null }) {
  const { settings } = useApp();
  const when = completedAt ? new Date(completedAt) : null;
  const base: ComputedRow[] = [
    ...rows,
    ...(settings ? [{ label: "Models", value: `${settings.answer_model} (answers) · ${settings.embed_model} (embeddings), run locally through Ollama` }] : []),
    { label: "Privacy", value: settings?.online_discovery ? "Online discovery is on. Only short search queries can leave this device." : "Everything ran on this machine. Nothing was sent anywhere." },
    ...(when ? [{ label: "Completed", value: when.toLocaleString() }] : []),
  ];
  return (
    <details className="computed">
      <summary>{label}<Icon name="chevron" size={14} /></summary>
      <div className="computed__body">
        {base.map((r) => <div key={r.label}><b>{r.label}</b><span>{r.value}</span></div>)}
      </div>
    </details>
  );
}

export function AnalysisTitle({
  title, description, actions, meta,
}: { title: string; description: string; actions?: ReactNode; meta?: string }) {
  return (
    <>
      <PageTitle title={title} description={description} actions={actions} />
      <div className="analysis-meta"><Disclaimer />{meta && <span>{meta}</span>}</div>
    </>
  );
}

export function Agreement({ status }: { status: FieldStatus | "agree" | "verify" | "confirmed" | "edited" }) {
  const tone = status === "verify" || status === "rejected" ? "amber" : status === "agree" ? "blue" : status === "not_reported" ? "neutral" : "teal";
  const showCheck = status === "agree" || status === "confirmed" || status === "edited";
  return <Pill tone={tone}>{showCheck && <Icon name="check" size={11} />}{FIELD_STATUS_LABEL[status] ?? status}</Pill>;
}
