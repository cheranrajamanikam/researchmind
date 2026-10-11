import { useEffect } from "react";
import { Link, Outlet, useLocation } from "react-router-dom";
import { Icon } from "@/components/Icon";
import { EmptyState } from "@/components/ui";
import { useApp } from "@/context/AppContext";
import { EvidenceProvider } from "@/context/EvidenceContext";
import { CopilotDrawer, EvidenceDrawer } from "./Drawers";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";

function Toasts() {
  const { toasts } = useApp();
  if (!toasts.length) return null;
  return (
    <div className="toast-stack" aria-live="polite">
      {toasts.map((t) => (
        <div key={t.id} className={`flow-toast ${t.kind === "error" ? "flow-toast--error" : ""}`} role={t.kind === "error" ? "alert" : "status"}>
          <Icon name={t.kind === "error" ? "close" : "check"} /><span>{t.message}</span>
        </div>
      ))}
    </div>
  );
}

export function AppShell() {
  const { copilotOpen, evidenceOpen, project } = useApp();
  const { pathname } = useLocation();

  useEffect(() => { document.getElementById("main")?.scrollTo?.({ top: 0 }); window.scrollTo?.({ top: 0 }); }, [pathname]);

  return (
    <EvidenceProvider>
      <div className="app">
        <a className="skip-link" href="#main">Skip to content</a>
        <Sidebar />
        <div className="app-main">
          <Topbar />
          <main className="content" id="main" tabIndex={-1}>
            {project || pathname.startsWith("/projects") || pathname === "/settings" ? <Outlet /> : (
              <div className="screen">
                <EmptyState icon="folder" title="Create your first project"
                  text="Projects keep papers, threads and decisions around one research question."
                  action={<Link className="button button--primary" to="/projects?new=1">New project</Link>} />
              </div>
            )}
          </main>
        </div>
        {evidenceOpen && <EvidenceDrawer />}
        {copilotOpen && <CopilotDrawer />}
        <Toasts />
      </div>
    </EvidenceProvider>
  );
}
