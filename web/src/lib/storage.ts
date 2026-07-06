import type { ModelSettings } from "../types";

export const MODEL_SETTINGS_KEY = "mirrorview:web:model-settings:v1";
export const CONSENT_ACCEPTED_KEY = "mirrorview:web:consent:v1";

export const defaultSettings: ModelSettings = {
  mode: "platform",
  provider: "deepseek",
  model: "deepseek-chat",
  apiKey: "",
  baseUrl: "",
  turnstileToken: "",
  apiBaseUrl: "/api"
};

export function loadSettings(): ModelSettings {
  try {
    const raw = localStorage.getItem(MODEL_SETTINGS_KEY);
    if (!raw) {
      return defaultSettings;
    }
    const parsed = JSON.parse(raw) as Partial<ModelSettings>;
    return {
      ...defaultSettings,
      ...parsed
    };
  } catch {
    return defaultSettings;
  }
}

export function saveSettings(settings: ModelSettings): void {
  localStorage.setItem(MODEL_SETTINGS_KEY, JSON.stringify(settings));
}

export function isConsentAccepted(): boolean {
  try {
    return localStorage.getItem(CONSENT_ACCEPTED_KEY) === "accepted";
  } catch {
    return false;
  }
}

export function setConsentAccepted(): void {
  localStorage.setItem(CONSENT_ACCEPTED_KEY, "accepted");
}
