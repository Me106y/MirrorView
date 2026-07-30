import { useEffect, useRef, useState } from "react";
import { useModelSettings } from "../context/ModelSettingsContext";

type Provider = 'deepseek' | 'openai';

const PROVIDER_CONFIG: Record<Provider, { baseUrl: string; model: string }> = {
  deepseek: { baseUrl: 'https://api.deepseek.com', model: 'deepseek-chat' },
  openai:   { baseUrl: 'https://api.openai.com',   model: 'gpt-4o-mini'   },
};

function detectProvider(baseUrl: string): Provider {
  if (baseUrl.toLowerCase().includes('openai')) return 'openai';
  return 'deepseek';
}

const SETTINGS_STATUS_KEY = "mirrorview:web:settings:test-status";

interface PersistedTestStatus {
  success: boolean;
  model: string;
  balance?: string;
  testedAt: number;
}

type TestState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "success"; message: string; balance?: string }
  | { kind: "error"; message: string };

function loadPersistedStatus(): PersistedTestStatus | null {
  try {
    const raw = localStorage.getItem(SETTINGS_STATUS_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as PersistedTestStatus;
    if (parsed && parsed.success && parsed.model) return parsed;
    return null;
  } catch {
    return null;
  }
}

function persistStatus(status: PersistedTestStatus | null): void {
  try {
    if (!status) {
      localStorage.removeItem(SETTINGS_STATUS_KEY);
    } else {
      localStorage.setItem(SETTINGS_STATUS_KEY, JSON.stringify(status));
    }
  } catch {
    // ignore
  }
}

export function SettingsPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { settings, updateSettings } = useModelSettings();
  const panelRef = useRef<HTMLElement | null>(null);

  const [draftModel, setDraftModel] = useState(settings.model);
  const [draftApiKey, setDraftApiKey] = useState(settings.apiKey);
  const [draftBaseUrl, setDraftBaseUrl] = useState(settings.baseUrl);
  const [provider, setProvider] = useState<Provider>(() => detectProvider(settings.baseUrl));
  const [testState, setTestState] = useState<TestState>({ kind: "idle" });
  const [persistedStatus, setPersistedStatus] = useState<PersistedTestStatus | null>(() => loadPersistedStatus());
  const [saveFlash, setSaveFlash] = useState(false);

  function selectProvider(p: Provider) {
    setProvider(p);
    setDraftBaseUrl(PROVIDER_CONFIG[p].baseUrl);
    setDraftModel(PROVIDER_CONFIG[p].model);
  }

  // Sync draft when settings change externally
  useEffect(() => {
    setDraftModel(settings.model);
    setDraftApiKey(settings.apiKey);
    setDraftBaseUrl(settings.baseUrl);
    setProvider(detectProvider(settings.baseUrl));
  }, [settings.model, settings.apiKey, settings.baseUrl]);

  // Reset transient state when panel opens/closes
  useEffect(() => {
    if (open) {
      setTestState({ kind: "idle" });
      setSaveFlash(false);
      setPersistedStatus(loadPersistedStatus());
    }
  }, [open]);

  // Focus trap + Escape
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
    setSaveFlash(true);
    window.setTimeout(() => setSaveFlash(false), 1400);
  };

  const handleClear = () => {
    updateSettings({
      model: "deepseek-chat",
      apiKey: "",
      baseUrl: "",
    });
    setDraftModel("deepseek-chat");
    setDraftApiKey("");
    setDraftBaseUrl("");
    setTestState({ kind: "idle" });
    setPersistedStatus(null);
    persistStatus(null);
  };

  const handleTest = async () => {
    if (!hasApiKey) {
      setTestState({ kind: "error", message: "请先填写 API Key 再测试连接。" });
      return;
    }
    setTestState({ kind: "loading" });
    try {
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

      const modelName = draftModel.trim() || "deepseek-chat";
      const next: PersistedTestStatus = {
        success: true,
        model: modelName,
        testedAt: Date.now(),
      };
      setPersistedStatus(next);
      persistStatus(next);
      setTestState({ kind: "success", message: "连接成功，API 可用。" });
    } catch (err) {
      setTestState({ kind: "error", message: (err as Error).message || "连接失败，请检查配置。" });
    }
  };

  // Show persisted status bar only when there is no active inline test feedback
  const showStatusBar =
    persistedStatus?.success &&
    testState.kind !== "loading" &&
    testState.kind !== "error";

  return (
    <div className="settings-overlay" onClick={onClose}>
      <aside
        className="settings-modal"
        ref={panelRef}
        role="dialog"
        aria-label="模型设置"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Head */}
        <div className="settings-modal-head">
          <h2>用你自己的模型</h2>
          <button className="settings-close-btn" onClick={onClose} aria-label="关闭设置">
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <line x1="1" y1="1" x2="13" y2="13" />
              <line x1="13" y1="1" x2="1" y2="13" />
            </svg>
          </button>
        </div>

        {/* Description */}
        <p className="settings-description">
          当前仅支持 DeepSeek 模型。API 密钥仅保存在浏览器本地，请求经服务端中转后直接调用模型，不做任何存储或日志记录，用完即走。
        </p>

        {/* Warning */}
        <p className="settings-warning">
          <span className="settings-warning-icon" aria-hidden="true">🔒</span>
          <span>介意的话，建议用一把临时 / 额度受限的 Key，用完即可吊销。</span>
        </p>

        {/* Provider segmented control */}
        <div className="provider-selector">
          <button
            type="button"
            className={`provider-btn${provider === 'deepseek' ? ' active' : ''}`}
            onClick={() => selectProvider('deepseek')}
          >
            DeepSeek
          </button>
          <button
            type="button"
            className={`provider-btn${provider === 'openai' ? ' active' : ''}`}
            onClick={() => selectProvider('openai')}
            disabled
            title="敬请期待"
          >
            OpenAI
            <span className="provider-btn-badge">敬请期待</span>
          </button>
        </div>

        {/* Status bar (persisted) */}
        {showStatusBar && (
          <div className="settings-status-bar">
            <span className="status-dot status-dot--green"></span>
            <span className="status-model">{persistedStatus!.model}</span>
            {persistedStatus!.balance && (
              <span className="status-balance">余额: {persistedStatus!.balance}</span>
            )}
          </div>
        )}

        {/* Form fields */}
        <div className="settings-field">
          <label htmlFor="sp-baseurl">Base URL</label>
          <input
            id="sp-baseurl"
            value={draftBaseUrl}
            onChange={(e) => setDraftBaseUrl(e.target.value)}
            placeholder="https://api.deepseek.com"
          />
        </div>

        <div className="settings-field">
          <label htmlFor="sp-apikey">API Key</label>
          <input
            id="sp-apikey"
            type="password"
            value={draftApiKey}
            onChange={(e) => setDraftApiKey(e.target.value)}
            placeholder="sk-..."
          />
        </div>

        <div className="settings-field">
          <label htmlFor="sp-model">Model</label>
          <input
            id="sp-model"
            value={draftModel}
            onChange={(e) => setDraftModel(e.target.value)}
            placeholder="deepseek-chat"
          />
        </div>

        {/* Inline test feedback */}
        {testState.kind === "loading" && (
          <div className="settings-test-result settings-test-result--success">
            正在测试连接...
          </div>
        )}
        {testState.kind === "success" && (
          <div className="settings-test-result settings-test-result--success">
            <span>✓ {testState.message}</span>
          </div>
        )}
        {testState.kind === "error" && (
          <div className="settings-test-result settings-test-result--error">
            ✕ {testState.message}
          </div>
        )}

        {/* Save flash */}
        {saveFlash && (
          <div className="settings-test-result settings-test-result--success">
            ✓ 已保存
          </div>
        )}

        {/* Actions */}
        <div className="settings-actions">
          <button
            className="settings-action-btn settings-action-btn--accent"
            onClick={handleTest}
            disabled={testState.kind === "loading"}
          >
            {testState.kind === "loading" ? "测试中..." : "测试可用"}
          </button>
          <button
            className="settings-action-btn settings-action-btn--primary"
            onClick={handleSave}
          >
            保存
          </button>
          <button
            className="settings-action-btn settings-action-btn--ghost"
            onClick={handleClear}
          >
            清除
          </button>
        </div>
      </aside>
    </div>
  );
}
