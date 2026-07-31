import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { gsap } from "gsap";
import type { ModelSettings } from "../types";
import { testCareerforgeRuntime } from "../lib/api";
import { createRuntimeStatus, hasFreshRuntimeStatus, loadRuntimeStatus, saveRuntimeStatus } from "../lib/runtimeStatus";

type GuardState =
  | { kind: "checking"; message: string }
  | { kind: "missing"; message: string }
  | { kind: "error"; message: string }
  | { kind: "ready"; message: string };

export function useCareerFeatureGuard(settings: ModelSettings, featureLabel: string) {
  const [state, setState] = useState<GuardState>({ kind: "checking", message: "正在校验模型连接…" });
  const modalRef = useRef<HTMLDivElement | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    let cancelled = false;

    async function run() {
      if (!settings.apiKey.trim()) {
        saveRuntimeStatus(null);
        if (!cancelled) {
          setState({ kind: "missing", message: `进入${featureLabel}前，请先在右上角「模型设置」中填写并测试 API Key。` });
        }
        return;
      }

      const persisted = loadRuntimeStatus();
      if (hasFreshRuntimeStatus(settings, persisted)) {
        if (!cancelled) {
          setState({ kind: "ready", message: "" });
        }
        return;
      }

      if (!cancelled) {
        setState({ kind: "checking", message: "正在校验模型连接，请稍候…" });
      }

      try {
        const resp = await testCareerforgeRuntime({
          provider: settings.provider,
          model: settings.model,
          apiKey: settings.apiKey,
          baseUrl: settings.baseUrl,
          apiBaseUrl: settings.apiBaseUrl,
        });
        const payload = (resp.result ?? resp) as Record<string, unknown>;
        if (!payload || payload.ok === false) {
          throw new Error(String(payload.message || resp.message || "模型连通性校验失败。"));
        }
        saveRuntimeStatus(createRuntimeStatus(settings));
        if (!cancelled) {
          setState({ kind: "ready", message: "" });
        }
      } catch (error) {
        saveRuntimeStatus(null);
        if (!cancelled) {
          setState({
            kind: "error",
            message: (error as Error).message || `进入${featureLabel}前，需要先修复模型连接。`,
          });
        }
      }
    }

    void run();
    return () => {
      cancelled = true;
    };
  }, [featureLabel, settings.apiBaseUrl, settings.apiKey, settings.baseUrl, settings.model, settings.provider]);

  useEffect(() => {
    if ((state.kind === "missing" || state.kind === "error") && modalRef.current) {
      gsap.fromTo(
        modalRef.current,
        { x: -10 },
        { x: 0, duration: 0.55, ease: "elastic.out(1, 0.32)", yoyo: true, repeat: 3 }
      );
    }
  }, [state.kind, state.message]);

  const overlay = state.kind === "ready" ? null : (
    <div className="feature-guard-overlay" role="presentation">
      <div className="feature-guard-modal" ref={modalRef} role="alertdialog" aria-modal="true" aria-label="模型连接提醒">
        <h3>{state.kind === "checking" ? "正在校验模型" : "请先完成模型配置"}</h3>
        <p>{state.message}</p>
        <p className="feature-guard-hint">请使用右上角「模型设置」配置你自己的 API Key；连接通过后即可继续。</p>
        {state.kind !== "checking" ? (
          <div className="feature-guard-actions">
            <button
              type="button"
              className="primary-btn feature-guard-btn"
              onClick={() => window.dispatchEvent(new Event("open-settings"))}
            >
              去设置
            </button>
            <button
              type="button"
              className="ghost-btn feature-guard-btn"
              onClick={() => navigate("/")}
            >
              返回首页
            </button>
          </div>
        ) : null}
      </div>
    </div>
  );

  return {
    blocked: state.kind !== "ready",
    checking: state.kind === "checking",
    overlay,
  };
}
