import { NavLink, Outlet, useLocation } from "react-router-dom";
import { useEffect, useRef, useState } from "react";
import { useAuth } from "../context/AuthContext";

export function Shell({ onOpenSettings }: { onOpenSettings: () => void }) {
  const location = useLocation();
  const isHome = location.pathname === "/";
  const { user, login, logout } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!menuOpen) {
      return;
    }

    const handlePointerDown = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    };

    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setMenuOpen(false);
      }
    };

    document.addEventListener("mousedown", handlePointerDown);
    document.addEventListener("keydown", handleEscape);

    return () => {
      document.removeEventListener("mousedown", handlePointerDown);
      document.removeEventListener("keydown", handleEscape);
    };
  }, [menuOpen]);

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
            <div className="user-menu" ref={menuRef}>
              <button
                type="button"
                className="user-avatar-trigger"
                onClick={() => setMenuOpen((open) => !open)}
                aria-haspopup="menu"
                aria-expanded={menuOpen}
                aria-label="打开用户菜单"
              >
                {user.avatar_url ? (
                  <img
                    className="user-avatar"
                    src={user.avatar_url}
                    alt="用户头像"
                    referrerPolicy="no-referrer"
                  />
                ) : (
                  <span className="user-avatar user-avatar-fallback" aria-hidden="true">
                    GH
                  </span>
                )}
              </button>
              {menuOpen ? (
                <div className="user-dropdown" role="menu">
                  <button
                    type="button"
                    className="user-dropdown-item"
                    role="menuitem"
                    onClick={async () => {
                      setMenuOpen(false);
                      await logout();
                    }}
                  >
                    退出登录
                  </button>
                </div>
              ) : null}
            </div>
          ) : isHome ? (
            <button className="topbar-action-btn github-login-btn" onClick={login}>
              通过 GitHub 登录
            </button>
          ) : (
            <button className="topbar-action-btn github-login-btn" onClick={login}>
              通过 GitHub 登录
            </button>
          )}
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
