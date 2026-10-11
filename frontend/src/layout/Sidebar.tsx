import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { Icon } from "@/components/Icon";
import { Pill } from "@/components/ui";
import { useApp } from "@/context/AppContext";
import { projectMark } from "@/lib/format";
import { NAV_GROUPS, isActive } from "@/routes";

export function Sidebar() {
  const { pathname } = useLocation();
  const nav = useNavigate();
  const { project, projects, selectProject, activeJobs, settings } = useApp();
  const [menu, setMenu] = useState(false);
  const online = settings?.online_discovery === true;

  return (
    <aside className="sidebar" aria-label="Primary">
      <button type="button" className="brand" onClick={() => nav("/")}>
        <span className="brand-mark">R</span><b>ResearchMind</b>
      </button>

      <div style={{ position: "relative" }}>
        <button type="button" className="project-switcher" aria-haspopup="menu" aria-expanded={menu} onClick={() => setMenu((m) => !m)}>
          <span className="project-mini">{projectMark(project?.name ?? "Project")}</span>
          <span><small>Current project</small><b>{project?.name ?? "No project"}</b></span>
          <Icon name="chevron" size={14} />
        </button>
        {menu && (
          <div className="project-menu" role="menu" onKeyDown={(e) => { if (e.key === "Escape") setMenu(false); }}>
            {projects.map((p) => (
              <button key={p.id} type="button" role="menuitemradio" aria-checked={p.id === project?.id}
                className={p.id === project?.id ? "active" : ""}
                onClick={() => { selectProject(p.id); setMenu(false); }}>
                <span className="project-mini">{projectMark(p.name)}</span><span>{p.name}</span>
              </button>
            ))}
            <button type="button" role="menuitem" onClick={() => { setMenu(false); nav("/projects?new=1"); }}>
              <Icon name="plus" size={14} /><span>New project…</span>
            </button>
          </div>
        )}
      </div>

      <nav aria-label="Sections">
        {NAV_GROUPS.map((g) => (
          <div className="nav-group" key={g.label}>
            <span>{g.label}</span>
            {g.items.map((item) => {
              const active = isActive(item.path, pathname);
              return (
                <button key={item.id} type="button" className={active ? "active" : ""} aria-current={active ? "page" : undefined}
                  onClick={() => nav(item.path)}>
                  <Icon name={item.icon} /><b>{item.label}</b>
                  {item.id === "upload" && activeJobs > 0 && <Pill tone="blue">{activeJobs}</Pill>}
                </button>
              );
            })}
          </div>
        ))}
      </nav>

      <div className="sidebar__bottom">
        <div className="local-card">
          <div><i /><b>{online ? "Online discovery on" : "Local mode"}</b></div>
          <span>{online ? "Short search queries may leave this device" : "Nothing leaves this device"}</span>
        </div>
        <button type="button" className={isActive("/settings", pathname) ? "active" : ""} onClick={() => nav("/settings")}>
          <Icon name="settings" /><b>Settings</b>
        </button>
      </div>
    </aside>
  );
}
