import { createContext, useContext, useMemo, useState } from "react";
import type { ModelSettings, RuntimeMode } from "../types";
import { defaultSettings, loadSettings, saveSettings } from "../lib/storage";

interface ModelSettingsContextValue {
  settings: ModelSettings;
  effectiveMode: RuntimeMode;
  updateSettings: (patch: Partial<ModelSettings>) => void;
}

const ModelSettingsContext = createContext<ModelSettingsContextValue | null>(null);

export function ModelSettingsProvider({ children }: { children: React.ReactNode }) {
  const [settings, setSettings] = useState<ModelSettings>(() => loadSettings());

  const updateSettings = (patch: Partial<ModelSettings>) => {
    setSettings((prev) => {
      const next = { ...prev, ...patch };
      saveSettings(next);
      return next;
    });
  };

  const value = useMemo<ModelSettingsContextValue>(() => {
    const effectiveMode: RuntimeMode = settings.mode === "byok" && settings.apiKey.trim() ? "byok" : "platform";
    return {
      settings,
      effectiveMode,
      updateSettings
    };
  }, [settings]);

  return <ModelSettingsContext.Provider value={value}>{children}</ModelSettingsContext.Provider>;
}

export function useModelSettings() {
  const value = useContext(ModelSettingsContext);
  if (!value) {
    throw new Error("useModelSettings must be used inside ModelSettingsProvider");
  }
  return value;
}

export function providerModelPlaceholder(provider: string): string {
  if (provider === "openai") {
    return "gpt-4o-mini";
  }
  if (provider === "anthropic") {
    return "claude-3-5-sonnet-latest";
  }
  return defaultSettings.model;
}
