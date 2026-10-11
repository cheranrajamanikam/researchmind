import { Navigate, Route, Routes } from "react-router-dom";
import { Skeleton } from "@/components/states";
import { useApp } from "@/context/AppContext";
import { AppShell } from "@/layout/AppShell";
import { FirstRun, SignIn, Unreachable } from "@/pages/Login";
import Overview from "@/pages/Overview";
import Library from "@/pages/Library";
import Upload from "@/pages/Upload";
import Viewer from "@/pages/Viewer";
import Search from "@/pages/Search";
import { ProjectDetail, Projects } from "@/pages/Projects";
import { ThreadDetail, Threads } from "@/pages/Threads";
import Settings from "@/pages/Settings";
import Evaluation from "@/pages/Evaluation";
import FindReferences from "@/pages/FindReferences";
import ReadingList from "@/pages/ReadingList";
import { ReceiptDetail, Receipts } from "@/pages/Receipts";
import ExtractionReview from "@/pages/ExtractionReview";
import PaperDiff from "@/pages/PaperDiff";
import Contradictions from "@/pages/Contradictions";
import NumericConsistency from "@/pages/NumericConsistency";
import Reproducibility from "@/pages/Reproducibility";
import Overclaim from "@/pages/Overclaim";
import CitationAudit from "@/pages/CitationAudit";
import PriorWork from "@/pages/PriorWork";
import GapMap from "@/pages/GapMap";
import PredictionGate from "@/pages/PredictionGate";
import DecisionLog from "@/pages/DecisionLog";
import Provenance from "@/pages/Provenance";

export default function App() {
  const { phase } = useApp();
  if (phase === "loading") {
    return <div className="login" style={{ placeItems: "center", display: "grid" }} role="status" aria-label="Loading"><Skeleton h={14} w={160} /></div>;
  }
  if (phase === "unreachable") return <Unreachable />;
  if (phase === "setup") return <FirstRun />;
  if (phase === "login") return <SignIn />;

  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Overview />} />
        <Route path="papers" element={<Library />} />
        <Route path="papers/:id" element={<Viewer />} />
        <Route path="upload" element={<Upload />} />
        <Route path="search" element={<Search />} />
        <Route path="projects" element={<Projects />} />
        <Route path="projects/:id" element={<ProjectDetail />} />
        <Route path="threads" element={<Threads />} />
        <Route path="threads/:id" element={<ThreadDetail />} />
        <Route path="evaluation" element={<Evaluation />} />
        <Route path="references" element={<FindReferences />} />
        <Route path="reading" element={<ReadingList />} />
        <Route path="receipts" element={<Receipts />} />
        <Route path="receipts/:id" element={<ReceiptDetail />} />
        <Route path="extraction" element={<ExtractionReview />} />
        <Route path="diff" element={<PaperDiff />} />
        <Route path="contradictions" element={<Contradictions />} />
        <Route path="numeric" element={<NumericConsistency />} />
        <Route path="reproducibility" element={<Reproducibility />} />
        <Route path="overclaim" element={<Overclaim />} />
        <Route path="audit" element={<CitationAudit />} />
        <Route path="prior-work" element={<PriorWork />} />
        <Route path="gaps" element={<GapMap />} />
        <Route path="prediction" element={<PredictionGate />} />
        <Route path="decisions" element={<DecisionLog />} />
        <Route path="provenance" element={<Provenance />} />
        <Route path="settings" element={<Settings />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
