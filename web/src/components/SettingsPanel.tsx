import { useModelSettings, providerModelPlaceholder } from "../context/ModelSettingsContext";

export function SettingsPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { settings, effectiveMode, updateSettings } = useModelSettings();

  if (!open) {
    return null;
  }

  return (
    <aside className="settings-panel">
      <div className="settings-header">
        <h3>模型设置</h3>
        <button className="ghost-btn" onClick={onClose}>
          关闭
        </button>
      </div>

      <label>
        模式
        <select value={settings.mode} onChange={(e) => updateSettings({ mode: e.target.value as "platform" | "byok" })}>
          <option value="platform">平台模型</option>
          <option value="byok">自带 API Key</option>
        </select>
      </label>

      <label>
        Provider
        <select
          value={settings.provider}
          onChange={(e) => {
            const provider = e.target.value as "deepseek" | "openai" | "anthropic";
            updateSettings({ provider, model: providerModelPlaceholder(provider) });
          }}
        >
          <option value="deepseek">DeepSeek</option>
          <option value="openai">OpenAI</option>
          <option value="anthropic">Anthropic</option>
        </select>
      </label>

      <label>
        Model
        <input value={settings.model} onChange={(e) => updateSettings({ model: e.target.value })} placeholder={providerModelPlaceholder(settings.provider)} />
      </label>

      <label>
        API Key
        <input
          type="password"
          value={settings.apiKey}
          onChange={(e) => updateSettings({ apiKey: e.target.value })}
          placeholder="仅 BYOK 模式需要"
        />
      </label>

      <label>
        Base URL (可选)
        <input value={settings.baseUrl} onChange={(e) => updateSettings({ baseUrl: e.target.value })} placeholder="留空使用默认" />
      </label>

      <label>
        Turnstile Token
        <input
          value={settings.turnstileToken}
          onChange={(e) => updateSettings({ turnstileToken: e.target.value })}
          placeholder="上线时由 Turnstile 组件注入"
        />
      </label>

      <label>
        API Base URL
        <input value={settings.apiBaseUrl} onChange={(e) => updateSettings({ apiBaseUrl: e.target.value })} placeholder="/api" />
      </label>

      <p className="settings-hint">当前生效模式：{effectiveMode === "byok" ? "BYOK" : "平台"}</p>
      <p className="settings-hint">密钥只保存在本地浏览器，不会上传到你自己的账号系统。</p>
    </aside>
  );
}
