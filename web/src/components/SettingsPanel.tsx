import { useModelSettings } from "../context/ModelSettingsContext";

export function SettingsPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { settings, updateSettings } = useModelSettings();

  if (!open) {
    return null;
  }

  return (
    <div className="settings-backdrop" onClick={onClose}>
      <aside className="settings-panel" onClick={(e) => e.stopPropagation()}>
        <div className="settings-header">
          <h3>模型设置</h3>
          <button className="ghost-btn" onClick={onClose}>
            关闭
          </button>
        </div>

        <label>
          Model
          <input
            value={settings.model}
            onChange={(e) => updateSettings({ model: e.target.value })}
            placeholder="deepseek-chat"
          />
        </label>

        <label>
          API Key
          <input
            type="password"
            value={settings.apiKey}
            onChange={(e) => updateSettings({ apiKey: e.target.value })}
            placeholder="留空则使用服务端默认 Key"
          />
        </label>

        <label>
          Base URL (可选)
          <input
            value={settings.baseUrl}
            onChange={(e) => updateSettings({ baseUrl: e.target.value })}
            placeholder="https://api.deepseek.com/v1"
          />
        </label>

        <p className="settings-hint">默认使用平台 DeepSeek 模型；这里填写会覆盖本次请求参数。</p>
        <p className="settings-hint">密钥仅保存在你的浏览器本地。</p>
      </aside>
    </div>
  );
}
