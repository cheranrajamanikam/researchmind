import type { ReactNode } from "react";
import { Icon, type IconName } from "./Icon";

export type Tone = "neutral" | "teal" | "blue" | "amber";

export function Button({
  children, icon, variant = "secondary", onClick, disabled = false, type = "button", title,
}: {
  children?: ReactNode; icon?: IconName; variant?: "primary" | "secondary" | "ghost" | "danger";
  onClick?: () => void; disabled?: boolean; type?: "button" | "submit"; title?: string;
}) {
  return (
    <button type={type} className={`button button--${variant}`} onClick={onClick} disabled={disabled} title={title}>
      {icon && <Icon name={icon} size={16} />}
      {children}
    </button>
  );
}

export function IconButton({
  icon, label, onClick, disabled,
}: { icon: IconName; label: string; onClick?: () => void; disabled?: boolean }) {
  return (
    <button type="button" className="icon-button" aria-label={label} title={label} onClick={onClick} disabled={disabled}>
      <Icon name={icon} />
    </button>
  );
}

export function Pill({ children, tone = "neutral" }: { children: ReactNode; tone?: Tone }) {
  return <span className={`pill pill--${tone}`}>{children}</span>;
}

export function PageTitle({
  eyebrow, title, description, actions,
}: { eyebrow?: string; title: string; description: string; actions?: ReactNode }) {
  return (
    <header className="page-title">
      <div>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {actions && <div className="page-title__actions">{actions}</div>}
    </header>
  );
}

export function EmptyState({
  icon = "archive", title, text, action,
}: { icon?: IconName; title: string; text: string; action?: ReactNode }) {
  return (
    <div className="empty-state">
      <div className="empty-state__icon"><Icon name={icon} size={24} /></div>
      <h3>{title}</h3>
      <p>{text}</p>
      {action}
    </div>
  );
}

export function Switch({
  checked, onChange, label, disabled,
}: { checked: boolean; onChange: (v: boolean) => void; label: string; disabled?: boolean }) {
  return (
    <span className="switch">
      <input type="checkbox" aria-label={label} checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
      <i />
    </span>
  );
}

export function Modal({
  title, children, onClose, actions,
}: { title: string; children: ReactNode; onClose: () => void; actions?: ReactNode }) {
  return (
    <div className="modal-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={title}
        onKeyDown={(e) => { if (e.key === "Escape") onClose(); }}>
        <h2>{title}</h2>
        {children}
        <div className="modal__actions">{actions}</div>
      </div>
    </div>
  );
}

export function Banner({
  tone = "info", icon = "help", title, children, action,
}: { tone?: "info" | "offline" | "review"; icon?: IconName; title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className={`banner banner--${tone}`} role={tone === "offline" ? "alert" : "status"}>
      <Icon name={icon} size={18} />
      <div><b>{title}</b>{children && <p>{children}</p>}</div>
      {action}
    </div>
  );
}
