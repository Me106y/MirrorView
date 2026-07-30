import { useEffect, useRef, useState } from "react";
import { useModelSettings } from "../context/ModelSettingsContext";
import { callCareerforgeSkill } from "../lib/api";

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
      const testSettings = {
        ...settings,
        model: draftModel || "deepseek-chat",
        apiKey: draftApiKey,
        baseUrl: draftBaseUrl,
      };
      const resp = await callCareerforgeSkill(testSettings, "/careerforge/test-connection", {
        message: "ping",
      });
      const balance = (resp as Record<string, unknown>).balance as string | undefined;
      const message = (resp as Record<string, unknown>).message as string | undefined;
      setTestState({
        kind: "success",
        message: message || "连接成功，API 可用。",
        balance: balance || undefined,
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
          <button className="ghost-btn" onClick={onClose} aria-label="关闭设置">
            ✕
          </button>
        </div>

        <label htmlFor="sp-model" title="模型标识符，如 deepseek-chat、gpt-4o。">
          Model
          <input
            id="sp-model"
            value={draftModel}
            onChange={(e) => setDraftModel(e.target.value)}
            placeholder="deepseek-chat"
            disabled={!editing}
          />
          <small style={{ color: 'var(--text-subtle, #888)', fontSize: '0.75rem' }}>
            如 deepseek-chat、gpt-4o
          </small>
        </label>

        <label htmlFor="sp-apikey" title="你的 API 密钥，仅存储在浏览器本地。">
          API Key
          <input
            id="sp-apikey"
            type="password"
            value={draftApiKey}
            onChange={(e) => setDraftApiKey(e.target.value)}
            placeholder="sk-..."
            disabled={!editing}
          />
          <small style={{ color: 'var(--text-subtle, #888)', fontSize: '0.75rem' }}>
            仅存储在浏览器本地
          </small>
        </label>

        <label htmlFor="sp-baseurl" title="API 服务的根地址。仅在自建代理时需要填写。">
          Base URL (可选)
          <input
            id="sp-baseurl"
            value={draftBaseUrl}
            onChange={(e) => setDraftBaseUrl(e.target.value)}
            placeholder="https://api.deepseek.com/v1"
            disabled={!editing}
          />
          <small style={{ color: 'var(--text-subtle, #888)', fontSize: '0.75rem' }}>
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
            className="ghost-btn"
            onClick={handleTest}
            disabled={testState.kind === "loading"}
            style={{ color: 'var(--accent)', borderColor: 'var(--accent)' }}
          >
            {testState.kind === "loading" ? "测试中..." : "测试可用"}
          </button>
          {editing || !isSaved ? (
            <button className="primary-btn" onClick={handleSave} style={{ marginTop: 0 }}>
              保存
            </button>
          ) : (
            <button className="ghost-btn" onClick={handleEdit}>
              修改
            </button>
          )}
        </div>
      </aside>
    </div>
  );
}
