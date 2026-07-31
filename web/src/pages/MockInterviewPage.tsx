import { FormEvent, useMemo, useState } from "react";
import { NavLink } from "react-router-dom";
import { callCareerforgeSkill } from "../lib/api";
import { useModelSettings } from "../context/ModelSettingsContext";
import { useCareerFeatureGuard } from "../components/CareerFeatureGuard";

type Msg = { role: "user" | "assistant"; content: string };

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export function MockInterviewPage() {
  const { settings } = useModelSettings();
  const featureGuard = useCareerFeatureGuard(settings, "模拟面试");
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<Msg[]>([]);
  const [loading, setLoading] = useState(false);

  const history = useMemo(
    () => messages.map((m) => ({ role: m.role === "assistant" ? "assistant" : "user", content: m.content })),
    [messages]
  );

  const send = async (e?: FormEvent) => {
    e?.preventDefault();
    const text = input.trim();
    if (!text || loading) {
      return;
    }

    setLoading(true);
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: text }, { role: "assistant", content: "" }]);

    try {
      const resp = await callCareerforgeSkill(settings, "/careerforge/agent/chat", {
        message: text,
        history
      });
      const answer = resp.reply || "系统未返回内容，请稍后重试。";
      const CHUNK = 16;
      for (let i = CHUNK; i <= answer.length + CHUNK; i += CHUNK) {
        await sleep(30);
        const partial = answer.slice(0, Math.min(i, answer.length));
        setMessages((prev) => {
          const next = [...prev];
          const idx = next.length - 1;
          if (idx >= 0 && next[idx].role === "assistant") {
            next[idx] = { role: "assistant", content: partial };
          }
          return next;
        });
      }
    } catch (err) {
      setMessages((prev) => {
        const next = [...prev];
        const idx = next.length - 1;
        if (idx >= 0) {
          next[idx] = { role: "assistant", content: (err as Error).message + "\n\n请重试" };
        }
        return next;
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      {featureGuard.overlay}
    <section className="mock-shell">
      <NavLink to="/" className="back-home-btn">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M19 12H5M12 19l-7-7 7-7"/>
        </svg>
        返回
      </NavLink>
      <article className="surface chat-panel">
        <h2>Mock Interview (文字版)</h2>
        <div className="chat-log" role="log" aria-live="polite">
          {messages.length === 0 ? <p className="muted">输入第一条消息开始面试。</p> : null}
          {messages.map((m, idx) => (
            <div key={`${m.role}-${idx}`} className={`msg ${m.role}`}>
              <span>{m.content}</span>
            </div>
          ))}
        </div>
        <form className="chat-input" onSubmit={send}>
          <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="例如：我想面试 AI 产品经理岗位" aria-label="输入消息" />
          <button className="primary-btn" disabled={loading}>
            {loading ? "生成中..." : "开始面试模拟"}
          </button>
        </form>
      </article>
    </section>
    </>
  );
}
