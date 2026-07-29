import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export function Shell({ onOpenSettings }: { onOpenSettings: () => void }) {
  const location = useLocation();
  const isHome = location.pathname === "/";
  const { user, logout } = useAuth();

  return (
    <div className="app-shell">
      <header className={`topbar${isHome ? " topbar-home" : ""}`}>
        <div className="topbar-brand-wrap">
          <NavLink to="/" className="topbar-brand-link">
            MirrorView
          </NavLink>
        </div>
        <div className="topbar-actions">
          <button className="ghost-btn topbar-action-btn" onClick={onOpenSettings}>
            模型设置
          </button>
          {user ? (
            <div className="user-menu">
              {user.avatar_url && (
                <img
                  className="user-avatar"
                  src={user.avatar_url}
                  alt={user.username}
                  referrerPolicy="no-referrer"
                />
              )}
              <span className="user-name">{user.username}</span>
              <button className="ghost-btn topbar-action-btn" onClick={logout}>
                登出
              </button>
            </div>
          ) : null}
        </div>
      </header>

      <main className="page-main">
        <Outlet />
      </main>

      <footer className="footer-bar">
        {isHome ? <p className="footer-home-note">智能求职训练平台 · 让求职更高效</p> : null}
        <nav className="footer-links">
          <NavLink to="/legal/privacy">隐私政策</NavLink>
          <NavLink to="/legal/terms">服务条款</NavLink>
          <NavLink to="/legal/ai-disclaimer">AI 免责声明</NavLink>
          <NavLink to="/legal/byok-risk">BYOK 风险提示</NavLink>
        </nav>
      </footer>
    </div>
  );
}
