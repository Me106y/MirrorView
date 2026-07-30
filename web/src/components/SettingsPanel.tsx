import { useEffect, useRef } from "react";
import { useModelSettings } from "../context/ModelSettingsContext";

export function SettingsPanel({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { settings, updateSettings } = useModelSettings();
  const panelRef = useRef<HTMLElement | null>(null);

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

  return (
    <div className="settings-backdrop" onClick={onClose}>
      <aside
        className="settings-panel"
        ref={panelRef}
        role="dialog"
        aria-label="模型设置"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="settings-header">
          <h3>模型设置</h3>
          <button className="ghost-btn" onClick={onClose} aria-label="关闭设置">
            关闭
          </button>
        </div>

        <label htmlFor="sp-model">
          Model
          <input
            id="sp-model"
            value={settings.model}
            onChange={(e) => updateSettings({ model: e.target.value })}
            placeholder="deepseek-chat"
          />
        </label>

        <label htmlFor="sp-apikey">
          API Key
          <input
            id="sp-apikey"
            type="password"
            value={settings.apiKey}
            onChange={(e) => updateSettings({ apiKey: e.target.value })}
            placeholder="留空则使用服务端默认 Key"
          />
        </label>

        <label htmlFor="sp-baseurl">
          Base URL (可选)
          <input
            id="sp-baseurl"
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
