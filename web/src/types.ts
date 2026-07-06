export type RuntimeMode = "platform" | "byok";
export type ModelProvider = "deepseek" | "openai" | "anthropic";

export interface ModelSettings {
  mode: RuntimeMode;
  provider: ModelProvider;
  model: string;
  apiKey: string;
  baseUrl: string;
  turnstileToken: string;
  apiBaseUrl: string;
}

export interface RuntimeMeta {
  runtime_mode: RuntimeMode;
  runtime_provider: ModelProvider;
}
