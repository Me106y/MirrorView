import {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
  type ReactNode,
} from "react";

export interface AuthUser {
  user_id: number;
  username: string;
  github_id: string | null;
  avatar_url: string | null;
}

interface AuthContextValue {
  user: AuthUser | null;
  loading: boolean;
  login: () => void;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue>({
  user: null,
  loading: true,
  login: () => {},
  logout: async () => {},
});

export function useAuth() {
  return useContext(AuthContext);
}

function resolveApiBase(): string {
  return "/api";
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const base = resolveApiBase();
    fetch(`${base}/auth/me`, { credentials: "include" })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (data && data.authenticated) {
          setUser({
            user_id: data.user_id,
            username: data.username,
            github_id: data.github_id ?? null,
            avatar_url: data.avatar_url ?? null,
          });
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const login = useCallback(() => {
    const base = resolveApiBase();
    const returnTo = encodeURIComponent(window.location.origin);
    window.location.href = `${base}/auth/github?return_to=${returnTo}`;
  }, []);

  const logout = useCallback(async () => {
    const base = resolveApiBase();
    try {
      await fetch(`${base}/auth/logout`, {
        credentials: "include",
        redirect: "manual",
      });
    } catch {
      // ignore network errors during logout
    }
    setUser(null);
    window.location.href = "/";
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}
