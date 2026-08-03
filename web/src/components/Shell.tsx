import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
export function Shell({ onOpenSettings }: { onOpenSettings: () => void }) {
  const location = useLocation();
  const isHome = location.pathname === "/";
  const { user, loading, login, logout } = useAuth();
  const [avatarMenuOpen, setAvatarMenuOpen] = useState(false);
  const avatarMenuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!avatarMenuOpen) {
      return;
    }

    function handlePointerDown(event: PointerEvent) {
      if (!avatarMenuRef.current?.contains(event.target as Node)) {
        setAvatarMenuOpen(false);
      }
    }

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setAvatarMenuOpen(false);
      }
    }

    window.addEventListener("pointerdown", handlePointerDown);
    window.addEventListener("keydown", handleKeyDown);

    return () => {
      window.removeEventListener("pointerdown", handlePointerDown);
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [avatarMenuOpen]);

  useEffect(() => {
    setAvatarMenuOpen(false);
  }, [user?.user_id]);

  const avatarLabel = user?.username?.slice(0, 2).toUpperCase() || "GH";
  const avatarAlt = user ? `${user.username} 的 GitHub 头像` : "GitHub 头像";

  return (
    <div className={`app-shell${location.pathname.startsWith("/resume-craft") ? " app-shell-resume-craft" : ""}`}>
      <header className={`topbar${isHome ? " topbar-home" : ""}`}>
        <div className="topbar-brand-wrap">
          <NavLink to="/" className="topbar-brand-link">
            MirrorView
          </NavLink>
        </div>
        <div className="topbar-actions">
          <button className="settings-btn topbar-action-btn" onClick={onOpenSettings}>
            <svg className="settings-btn-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <circle cx="12" cy="12" r="3"/>
              <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>
            </svg>
            模型设置
          </button>
          {!loading && !user ? (
            <button className="github-login-btn topbar-action-btn" onClick={login}>
              GitHub登录
            </button>
          ) : null}
          {user ? (
            <div className="user-menu" ref={avatarMenuRef}>
              <button
                type="button"
                className="user-avatar-trigger"
                aria-label="打开账户菜单"
                aria-expanded={avatarMenuOpen}
                onClick={() => setAvatarMenuOpen((value) => !value)}
              >
                {user.avatar_url ? (
                  <img className="user-avatar" src={user.avatar_url} alt={avatarAlt} />
                ) : (
                  <span className="user-avatar-fallback" aria-hidden="true">
                    {avatarLabel}
                  </span>
                )}
              </button>
              {avatarMenuOpen ? (
                <div className="user-dropdown" role="menu" aria-label="账户菜单">
                  <button
                    type="button"
                    className="user-dropdown-item"
                    role="menuitem"
                    onClick={() => {
                      setAvatarMenuOpen(false);
                      void logout();
                    }}
                  >
                    登出
                  </button>
                </div>
              ) : null}
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
