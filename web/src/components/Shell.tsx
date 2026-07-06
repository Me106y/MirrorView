import { NavLink, Outlet, useLocation } from "react-router-dom";

export function Shell({ onOpenSettings }: { onOpenSettings: () => void }) {
  const location = useLocation();
  const isHome = location.pathname === "/";

  return (
    <div className="app-shell">
      <header className={`topbar${isHome ? " topbar-home" : ""}`}>
        <div>
          {isHome ? <span className="topbar-mark">MirrorView</span> : <h1>MirrorView Web</h1>}
          {isHome ? null : <p>Phase A Week 1 · Public MVP</p>}
        </div>
        <div className="topbar-actions">
          <button className="ghost-btn topbar-action-btn" onClick={onOpenSettings}>
            模型设置
          </button>
          {isHome ? (
            <a
              className="primary-btn topbar-action-btn github-login-btn"
              href="https://github.com/login"
              target="_blank"
              rel="noreferrer"
            >
              GitHub 登录
            </a>
          ) : null}
        </div>
      </header>

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
