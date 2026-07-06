import { Route, Routes } from "react-router-dom";
import { Shell } from "./components/Shell";
import { SettingsPanel } from "./components/SettingsPanel";
import { ResumeMatchPage } from "./pages/ResumeMatchPage";
import { ResumeCraftPage } from "./pages/ResumeCraftPage";
import { CoverLetterPage } from "./pages/CoverLetterPage";
import { MockInterviewPage } from "./pages/MockInterviewPage";
import { JobHuntPage } from "./pages/JobHuntPage";
import { HomePage } from "./pages/HomePage";
import { PrivacyPage } from "./pages/legal/PrivacyPage";
import { TermsPage } from "./pages/legal/TermsPage";
import { AiDisclaimerPage } from "./pages/legal/AiDisclaimerPage";
import { ByokRiskPage } from "./pages/legal/ByokRiskPage";
import { useState } from "react";
import { ConsentModal } from "./components/ConsentModal";
import { Analytics } from "@vercel/analytics/react";
import { SpeedInsights } from "@vercel/speed-insights/react";

export default function App() {
  const [settingsOpen, setSettingsOpen] = useState(false);

  return (
    <>
      <Routes>
        <Route element={<Shell onOpenSettings={() => setSettingsOpen(true)} />}>
          <Route path="/" element={<HomePage />} />
          <Route path="/resume-match" element={<ResumeMatchPage />} />
          <Route path="/resume-craft" element={<ResumeCraftPage />} />
          <Route path="/cover-letter" element={<CoverLetterPage />} />
          <Route path="/mock-interview" element={<MockInterviewPage />} />
          <Route path="/job-hunt" element={<JobHuntPage />} />
          <Route path="/legal/privacy" element={<PrivacyPage />} />
          <Route path="/legal/terms" element={<TermsPage />} />
          <Route path="/legal/ai-disclaimer" element={<AiDisclaimerPage />} />
          <Route path="/legal/byok-risk" element={<ByokRiskPage />} />
        </Route>
      </Routes>
      <SettingsPanel open={settingsOpen} onClose={() => setSettingsOpen(false)} />
      <ConsentModal />
      <Analytics />
      <SpeedInsights />
    </>
  );
}
