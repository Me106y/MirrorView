import { useEffect, useRef, useState } from "react";
import { useModelSettings } from "../context/ModelSettingsContext";
import { testCareerforgeRuntime } from "../lib/api";
import { createRuntimeStatus, loadRuntimeStatus, saveRuntimeStatus, type PersistedRuntimeStatus } from "../lib/runtimeStatus";

type Provider = 'deepseek' | 'openai' | 'ccswitch';

const PROVIDER_CONFIG: Record<Provider, { baseUrl: string; model: string }> = {
  deepseek:  { baseUrl: 'https://api.deepseek.com', model: 'deepseek-chat' },
  openai:    { baseUrl: 'https://api.openai.com',   model: 'gpt-4o-mini'   },
  ccswitch:  { baseUrl: 'https://modelsell.com/v1',  model: 'deepseek-v4-flash' },
};

function detectProvider(baseUrl: string): Provider {
  const lower = baseUrl.toLowerCase();
  if (lower.includes('openai')) return 'openai';
  if (lower.includes('modelsell')) return 'ccswitch';
  return 'deepseek';
}

interface CcSwitchModel {
  id: string;
  object: string;
  created: number;
  owned_by: string;
  supported_endpoint_types: string[];
}

type ModelListState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "loaded"; models: CcSwitchModel[] }
  | { kind: "error"; message: string };

type TestState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "success"; message: string }
  | { kind: "error"; message: string };

export function SettingsPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { settings, updateSettings } = useModelSettings();
  const panelRef = useRef<HTMLElement | null>(null);

  const [draftModel, setDraftModel] = useState(settings.model);
  const [draftApiKey, setDraftApiKey] = useState(settings.apiKey);
  const [draftBaseUrl, setDraftBaseUrl] = useState(settings.baseUrl);
  const [provider, setProvider] = useState<Provider>(() => detectProvider(settings.baseUrl));
  const [testState, setTestState] = useState<TestState>({ kind: "idle" });
  const [persistedStatus, setPersistedStatus] = useState<PersistedRuntimeStatus | null>(() => loadRuntimeStatus());
  const [saveFlash, setSaveFlash] = useState(false);
  const [modelListState, setModelListState] = useState<ModelListState>({ kind: "idle" });
  const modelListCache = useRef<Record<string, CcSwitchModel[]>>({});

  function selectProvider(p: Provider) {
    setProvider(p);
    setDraftBaseUrl(PROVIDER_CONFIG[p].baseUrl);
    setDraftModel(PROVIDER_CONFIG[p].model);
    setModelListState({ kind: "idle" });
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
      setPersistedStatus(loadRuntimeStatus());
    }
  }, [open]);

  // Fetch model list when CC Switch is selected and API key is available
  useEffect(() => {
    if (provider !== 'ccswitch') return;
    const key = draftApiKey.trim();
    if (!key) return;

    const baseUrl = draftBaseUrl.trim().replace(/\/+$/, '');
    const cacheKey = `${baseUrl}|${key}`;

    // Check cache
    if (modelListCache.current[cacheKey]) {
      setModelListState({ kind: "loaded", models: modelListCache.current[cacheKey] });
      // If model is still the default, select first from list
      setDraftModel((prev) => {
        if (prev === PROVIDER_CONFIG.ccswitch.model && modelListCache.current[cacheKey].length > 0) {
          return modelListCache.current[cacheKey][0].id;
        }
        return prev;
      });
      return;
    }

    let cancelled = false;
    setModelListState({ kind: "loading" });

    const url = `${baseUrl}/models`;
    fetch(url, {
      headers: { "Authorization": `Bearer ${key}` }
    })
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json() as Promise<{ data: CcSwitchModel[] }>;
      })
      .then((json) => {
        if (cancelled) return;
        const models = (json.data || []).filter(
          (m) => m.supported_endpoint_types && m.supported_endpoint_types.includes("openai")
        );
        if (models.length === 0) {
          setModelListState({ kind: "error", message: "未找到支持 OpenAI 聊天格式的模型。" });
          return;
        }
        modelListCache.current[cacheKey] = models;
        setModelListState({ kind: "loaded", models });
        // Select first model
        setDraftModel(models[0].id);
      })
      .catch((err) => {
        if (cancelled) return;
        setModelListState({ kind: "error", message: `加载模型列表失败: ${err instanceof Error ? err.message : '未知错误'}` });
      });

    return () => { cancelled = true; };
  }, [provider, draftApiKey, draftBaseUrl]);

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
      provider: provider,
      model: draftModel,
      apiKey: draftApiKey,
      baseUrl: draftBaseUrl,
    });
    setSaveFlash(true);
    window.setTimeout(() => setSaveFlash(false), 1400);
  };

  const handleClear = () => {
    updateSettings({
      provider: "deepseek",
      model: "deepseek-chat",
      apiKey: "",
      baseUrl: "",
    });
    setProvider("deepseek");
    setDraftModel("deepseek-chat");
    setDraftApiKey("");
    setDraftBaseUrl("");
    setTestState({ kind: "idle" });
    setPersistedStatus(null);
    setModelListState({ kind: "idle" });
    saveRuntimeStatus(null);
  };

  const handleTest = async () => {
    if (!hasApiKey) {
      setTestState({ kind: "error", message: "请先填写 API Key 再测试连接。" });
      return;
    }
    setTestState({ kind: "loading" });
    try {
      const resp = await testCareerforgeRuntime({
        provider: provider,
        model: draftModel.trim() || "deepseek-chat",
        apiKey: draftApiKey.trim(),
        baseUrl: draftBaseUrl.trim(),
        apiBaseUrl: settings.apiBaseUrl,
      });
      const payload = (resp.result ?? resp) as Record<string, unknown>;
      if (payload.ok === false) {
        throw new Error((payload.message as string) || resp.message || "连接失败，请检查配置。");
      }

      const next = createRuntimeStatus({
        provider: provider,
        model: draftModel.trim() || "deepseek-chat",
        apiKey: draftApiKey.trim(),
        baseUrl: draftBaseUrl.trim(),
      });
      setPersistedStatus(next);
      saveRuntimeStatus(next);
      setTestState({ kind: "success", message: "连接成功，API 可用。" });
    } catch (err) {
      saveRuntimeStatus(null);
      setPersistedStatus(null);
      setTestState({ kind: "error", message: err instanceof Error ? err.message : "连接失败，请检查配置。" });
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
          DeepSeek 和 CC Switch 模型可用。API 密钥仅保存在浏览器本地，请求经服务端中转后直接调用模型，不做任何存储或日志记录，用完即走。
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
          <button
            type="button"
            className={`provider-btn${provider === 'ccswitch' ? ' active' : ''}`}
            onClick={() => selectProvider('ccswitch')}
          >
            CC Switch
          </button>
        </div>

        {/* Status bar (persisted) */}
        {showStatusBar && (
          <div className="settings-status-bar">
            <span className="status-dot status-dot--green"></span>
            <span className="status-model">{persistedStatus!.model}</span>
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

        {/* Model field: dropdown for CC Switch, text input for others */}
        {provider === 'ccswitch' ? (
          <div className="settings-field">
            <label htmlFor="sp-model">Model</label>
            {modelListState.kind === "loading" && (
              <div className="settings-model-loading">正在加载模型列表…</div>
            )}
            {modelListState.kind === "error" && (
              <>
                <div className="settings-test-result settings-test-result--error">
                  ✕ {modelListState.message}
                </div>
                <input
                  id="sp-model"
                  value={draftModel}
                  onChange={(e) => setDraftModel(e.target.value)}
                  placeholder="deepseek-v4-flash"
                />
              </>
            )}
            {modelListState.kind === "loaded" && (
              <>
                <select
                  id="sp-model"
                  className="settings-model-select"
                  value={draftModel}
                  onChange={(e) => setDraftModel(e.target.value)}
                >
                  {modelListState.models.map((m) => (
                    <option key={m.id} value={m.id}>{m.id}</option>
                  ))}
                </select>
                <p className="settings-model-hint">仅显示支持 OpenAI 聊天格式的模型</p>
              </>
            )}
            {modelListState.kind === "idle" && (
              <input
                id="sp-model"
                value={draftModel}
                onChange={(e) => setDraftModel(e.target.value)}
                placeholder="deepseek-v4-flash"
              />
            )}
          </div>
        ) : (
          <div className="settings-field">
            <label htmlFor="sp-model">Model</label>
            <input
              id="sp-model"
              value={draftModel}
              onChange={(e) => setDraftModel(e.target.value)}
              placeholder="deepseek-chat"
            />
          </div>
        )}

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
