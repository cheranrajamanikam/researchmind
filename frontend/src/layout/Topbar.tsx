import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Icon } from "@/components/Icon";
import { IconButton } from "@/components/ui";
import { useApp } from "@/context/AppContext";
import { initials } from "@/lib/format";

export function Topbar() {
  const nav = useNavigate();
  const { settings, dark, toggleTheme, copilotOpen, setCopilotOpen, evidenceOpen, setEvidenceOpen, userName, signOut, activeJobs } = useApp();
  const [menu, setMenu] = useState(false);
  const online = settings?.online_discovery === true;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        nav("/search");
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [nav]);

  return (
    <header className="topbar">
      <button type="button" className="global-search" onClick={() => nav("/search")}>
        <Icon name="search" size={16} /><span>Search papers, evidence, threads…</span><kbd>Ctrl K</kbd>
      </button>
      <div className="topbar__actions">
        {activeJobs > 0 && (
          <button type="button" className="mode-indicator" onClick={() => nav("/upload")} aria-label={`${activeJobs} papers processing`}>
            <span className="spinner" />{activeJobs} processing
          </button>
        )}
        <span className={`mode-indicator ${online ? "online" : ""}`} role="status">
          <i />{online ? "Online discovery active" : "Local mode"}
        </span>
        <IconButton icon={dark ? "sun" : "moon"} label={dark ? "Switch to light theme" : "Switch to dark theme"} onClick={toggleTheme} />
        <IconButton icon="thread" label={copilotOpen ? "Close copilot" : "Open copilot"} onClick={() => { setCopilotOpen(!copilotOpen); setEvidenceOpen(false); }} />
        <IconButton icon="archive" label={evidenceOpen ? "Close evidence panel" : "Open evidence panel"} onClick={() => { setEvidenceOpen(!evidenceOpen); setCopilotOpen(false); }} />
        <div style={{ position: "relative" }}>
          <button type="button" className="avatar" aria-haspopup="menu" aria-expanded={menu} aria-label="Account menu" onClick={() => setMenu((m) => !m)}>
            {initials(userName || "Me")}
          </button>
          {menu && (
            <div className="project-menu project-menu--right" role="menu" onKeyDown={(e) => { if (e.key === "Escape") setMenu(false); }}>
              <div className="project-menu__label">{userName || "Local user"}</div>
              <button type="button" role="menuitem" onClick={() => { setMenu(false); nav("/settings"); }}><Icon name="settings" size={14} /><span>Settings</span></button>
              <button type="button" role="menuitem" onClick={() => { setMenu(false); signOut(); }}><Icon name="close" size={14} /><span>Lock workspace</span></button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
