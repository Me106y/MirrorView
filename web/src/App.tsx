import { Route, Routes, Navigate } from "react-router-dom";
import { Shell } from "./components/Shell";
import { SettingsPanel } from "./components/SettingsPanel";
import { ResumeMatchPage } from "./pages/ResumeMatchPage";
import { ResumeCraftPage } from "./pages/ResumeCraftPage";
import { CoverLetterPage } from "./pages/CoverLetterPage";
import { MockInterviewPage } from "./pages/MockInterviewPage";
import { JobHuntPage } from "./pages/JobHuntPage";
import { HomePage } from "./pages/HomePage";
import { LoginPage } from "./pages/LoginPage";
import { PrivacyPage } from "./pages/legal/PrivacyPage";
import { TermsPage } from "./pages/legal/TermsPage";
import { AiDisclaimerPage } from "./pages/legal/AiDisclaimerPage";
import { ByokRiskPage } from "./pages/legal/ByokRiskPage";
import { useState } from "react";
import { ConsentModal } from "./components/ConsentModal";
import { Analytics } from "@vercel/analytics/react";
import { useAuth } from "./context/AuthContext";
import type { JSX } from "react";

function ProtectedShell({ onOpenSettings }: { onOpenSettings: () => void }) {
  const { loading } = useAuth();
  if (loading) return null;
  return <Shell onOpenSettings={onOpenSettings} />;
}

function RequireAuth({ children }: { children: JSX.Element }) {
  const { user, loading } = useAuth();
  if (loading) return null;
  if (!user) return <Navigate to="/" replace />;
  return children;
}

export default function App() {
  const [settingsOpen, setSettingsOpen] = useState(false);

  return (
    <>
      <Routes>
        <Route path="/login" element={<Navigate to="/" replace />} />
        <Route element={<ProtectedShell onOpenSettings={() => setSettingsOpen(true)} />}>
          <Route path="/" element={<HomePage />} />
          <Route path="/resume-match" element={<RequireAuth><ResumeMatchPage /></RequireAuth>} />
          <Route path="/resume-craft" element={<RequireAuth><ResumeCraftPage /></RequireAuth>} />
          <Route path="/cover-letter" element={<RequireAuth><CoverLetterPage /></RequireAuth>} />
          <Route path="/mock-interview" element={<RequireAuth><MockInterviewPage /></RequireAuth>} />
          <Route path="/job-hunt" element={<RequireAuth><JobHuntPage /></RequireAuth>} />
          <Route path="/legal/privacy" element={<PrivacyPage />} />
          <Route path="/legal/terms" element={<TermsPage />} />
          <Route path="/legal/ai-disclaimer" element={<AiDisclaimerPage />} />
          <Route path="/legal/byok-risk" element={<ByokRiskPage />} />
        </Route>
      </Routes>
      <SettingsPanel open={settingsOpen} onClose={() => setSettingsOpen(false)} />
      <ConsentModal />
      <Analytics />
    </>
  );
}
