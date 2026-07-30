import { useEffect, useState } from "react";

function resolveApiBase(): string {
  const host = window.location.hostname.toLowerCase();
  if (host === "localhost" || host === "127.0.0.1") {
    return "/api";
  }
  return "";
}

export function OAuthCallbackPage() {
  const [message, setMessage] = useState("正在完成 GitHub 登录...");

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const code = params.get("code")?.trim() || "";
    const state = params.get("state")?.trim() || "";

    if (!code || !state) {
      setMessage("缺少 GitHub 授权参数，请返回首页重新发起登录。");
      return;
    }

    const controller = new AbortController();
    const base = resolveApiBase();

    fetch(`${base}/auth/github/exchange`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      credentials: "include",
      body: JSON.stringify({ code, state }),
      signal: controller.signal
    })
      .then(async (response) => {
        const data = (await response.json().catch(() => null)) as
          | { redirect_to?: string; message?: string; error?: string }
          | null;

        if (!response.ok) {
          throw new Error(data?.message || data?.error || `GitHub 登录失败（${response.status}）`);
        }

        const target = data?.redirect_to || "/";
        window.location.replace(target);
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) {
          return;
        }
        const text = error instanceof Error ? error.message : "GitHub 登录失败，请稍后重试。";
        setMessage(text);
      });

    return () => controller.abort();
  }, []);

  return (
    <section className="oauth-callback-page">
      <div className="oauth-callback-card">
        <h2>GitHub 登录</h2>
        <p>{message}</p>
      </div>
    </section>
  );
}
