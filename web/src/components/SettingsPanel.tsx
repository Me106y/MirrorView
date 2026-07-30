import { useEffect, useRef, useState } from "react";
import { useModelSettings } from "../context/ModelSettingsContext";

type TestState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "success"; message: string; balance?: string }
  | { kind: "error"; message: string };

export function SettingsPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { settings, updateSettings } = useModelSettings();
  const panelRef = useRef<HTMLElement | null>(null);

  // Local draft state for editing
  const [draftModel, setDraftModel] = useState(settings.model);
  const [draftApiKey, setDraftApiKey] = useState(settings.apiKey);
  const [draftBaseUrl, setDraftBaseUrl] = useState(settings.baseUrl);
  const [editing, setEditing] = useState(false);
  const [testState, setTestState] = useState<TestState>({ kind: "idle" });

  // Sync draft when settings change externally
  useEffect(() => {
    setDraftModel(settings.model);
    setDraftApiKey(settings.apiKey);
    setDraftBaseUrl(settings.baseUrl);
  }, [settings.model, settings.apiKey, settings.baseUrl]);

  // Reset test state when panel opens/closes
  useEffect(() => {
    if (open) {
      setTestState({ kind: "idle" });
      setEditing(false);
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const panel = panelRef.current;
    if (!panel) return;

    const focusable = panel.querySelectorAll<HTMLElement>(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    );
    const first = focusable[0];
    const last = focusable[focusable.length - 1];

    first?.focus();

    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") {
        onClose();
        return;
      }
      if (e.key !== "Tab") return;
      if (e.shiftKey) {
        if (document.activeElement === first) { e.preventDefault(); last?.focus(); }
      } else {
        if (document.activeElement === last) { e.preventDefault(); first?.focus(); }
      }
    }

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [open, onClose]);

  if (!open) {
    return null;
  }

  const hasApiKey = draftApiKey.trim().length > 0;

  const handleSave = () => {
    updateSettings({
      model: draftModel,
      apiKey: draftApiKey,
      baseUrl: draftBaseUrl,
    });
    setEditing(false);
    setTestState({ kind: "idle" });
  };

  const handleEdit = () => {
    setEditing(true);
  };

  const handleTest = async () => {
    if (!hasApiKey) {
      setTestState({ kind: "error", message: "请先填写 API Key 再测试连接。" });
      return;
    }
    setTestState({ kind: "loading" });
    try {
      // Build the base URL for direct LLM API call
      const rawBase = draftBaseUrl.trim() || "https://api.deepseek.com";
      const normalizedBase = rawBase.endsWith("/v1") || rawBase.endsWith("/v1/")
        ? rawBase.replace(/\/+$/, "")
        : rawBase.replace(/\/+$/, "") + "/v1";
      const url = `${normalizedBase}/chat/completions`;

      const resp = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": `Bearer ${draftApiKey.trim()}`,
        },
        body: JSON.stringify({
          model: draftModel.trim() || "deepseek-chat",
          messages: [{ role: "user", content: "hi" }],
          max_tokens: 5,
        }),
      });

      if (!resp.ok) {
        let errMsg = `Request failed (${resp.status})`;
        try {
          const errData = await resp.json();
          const detail = (errData as Record<string, unknown>).error as Record<string, unknown> | undefined;
          if (detail && typeof detail.message === "string") {
            errMsg = detail.message;
          } else if (typeof (errData as Record<string, unknown>).message === "string") {
            errMsg = (errData as Record<string, unknown>).message as string;
          }
        } catch { /* ignore parse error */ }
        throw new Error(errMsg);
      }

      setTestState({
        kind: "success",
        message: "连接成功，API 可用。",
      });
    } catch (err) {
      setTestState({ kind: "error", message: (err as Error).message || "连接失败，请检查配置。" });
    }
  };

  const isSaved =
    draftModel === settings.model &&
    draftApiKey === settings.apiKey &&
    draftBaseUrl === settings.baseUrl;

  return (
    <div className="settings-overlay" onClick={onClose}>
      <aside
        className="settings-modal"
        ref={panelRef}
        role="dialog"
        aria-label="模型设置"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="settings-modal-head">
          <h2>模型设置</h2>
          <button className="settings-close-btn" onClick={onClose} aria-label="关闭设置">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <line x1="1" y1="1" x2="13" y2="13" />
              <line x1="13" y1="1" x2="1" y2="13" />
            </svg>
          </button>
        </div>

        <label htmlFor="sp-model" className="settings-label" title="模型标识符，如 deepseek-chat、gpt-4o。">
          <span className="settings-label-text">Model</span>
          <input
            id="sp-model"
            value={draftModel}
            onChange={(e) => setDraftModel(e.target.value)}
            placeholder="deepseek-chat"
            disabled={!editing}
          />
          <small className="settings-label-hint">
            如 deepseek-chat、gpt-4o
          </small>
        </label>

        <label htmlFor="sp-apikey" className="settings-label" title="你的 API 密钥，仅存储在浏览器本地。">
          <span className="settings-label-text">API Key</span>
          <input
            id="sp-apikey"
            type="password"
            value={draftApiKey}
            onChange={(e) => setDraftApiKey(e.target.value)}
            placeholder="sk-..."
            disabled={!editing}
          />
          <small className="settings-label-hint">
            仅存储在浏览器本地
          </small>
        </label>

        <label htmlFor="sp-baseurl" className="settings-label" title="API 服务的根地址。仅在自建代理时需要填写。">
          <span className="settings-label-text">Base URL <span className="settings-label-optional">(可选)</span></span>
          <input
            id="sp-baseurl"
            value={draftBaseUrl}
            onChange={(e) => setDraftBaseUrl(e.target.value)}
            placeholder="https://api.deepseek.com/v1"
            disabled={!editing}
          />
          <small className="settings-label-hint">
            仅在自建代理时需要填写
          </small>
        </label>

        {!hasApiKey && (
          <p className="settings-hint" style={{ color: 'var(--error, #a33232)' }}>
            请先在模型设置中配置你的 API 密钥
          </p>
        )}

        {testState.kind === "loading" && (
          <div className="settings-test-result settings-test-result--success">
            正在测试连接...
          </div>
        )}
        {testState.kind === "success" && (
          <div className="settings-test-result settings-test-result--success">
            <span>✓ {testState.message}</span>
            {testState.balance && (
              <span className="settings-balance">余额: {testState.balance}</span>
            )}
          </div>
        )}
        {testState.kind === "error" && (
          <div className="settings-test-result settings-test-result--error">
            ✕ {testState.message}
          </div>
        )}

        <div className="settings-actions">
          <button
            className="settings-action-btn settings-action-btn--outline"
            onClick={handleTest}
            disabled={testState.kind === "loading"}
          >
            {testState.kind === "loading" ? "测试中..." : "测试可用"}
          </button>
          {editing || !isSaved ? (
            <button className="settings-action-btn settings-action-btn--primary" onClick={handleSave}>
              保存
            </button>
          ) : (
            <button className="settings-action-btn settings-action-btn--outline" onClick={handleEdit}>
              修改
            </button>
          )}
        </div>
      </aside>
    </div>
  );
}
