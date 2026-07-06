import { NavLink, Outlet } from "react-router-dom";

export function Shell({ onOpenSettings }: { onOpenSettings: () => void }) {
  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <h1>MirrorView Web</h1>
          <p>Phase A Week 1 · Public MVP</p>
        </div>
        <button className="primary-btn" onClick={onOpenSettings}>
          模型设置
        </button>
      </header>

      <nav className="nav-grid">
        <NavLink to="/resume-match">Resume Match</NavLink>
        <NavLink to="/resume-craft">Resume Craft</NavLink>
        <NavLink to="/cover-letter">Cover Letter</NavLink>
        <NavLink to="/mock-interview">Mock Interview</NavLink>
        <NavLink to="/job-hunt">Job Hunt</NavLink>
      </nav>

      <main className="page-main">
        <Outlet />
      </main>

      <footer className="footer-bar">
        <NavLink to="/legal/privacy">隐私政策</NavLink>
        <NavLink to="/legal/terms">服务条款</NavLink>
        <NavLink to="/legal/ai-disclaimer">AI 免责声明</NavLink>
        <NavLink to="/legal/byok-risk">BYOK 风险提示</NavLink>
      </footer>
    </div>
  );
}
