import { FormEvent, useMemo, useState } from "react";
import { callCareerforgeSkill } from "../lib/api";
import { useModelSettings } from "../context/ModelSettingsContext";

type Msg = { role: "user" | "assistant"; content: string };

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export function MockInterviewPage() {
  const { settings } = useModelSettings();
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
      for (let i = 1; i <= answer.length; i += 1) {
        await sleep(12);
        const partial = answer.slice(0, i);
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
          next[idx] = { role: "assistant", content: (err as Error).message };
        }
        return next;
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="mock-shell">
      <article className="surface chat-panel">
        <h2>Mock Interview (文字版)</h2>
        <div className="chat-log">
          {messages.length === 0 ? <p className="muted">输入第一条消息开始面试。</p> : null}
          {messages.map((m, idx) => (
            <div key={`${m.role}-${idx}`} className={`msg ${m.role}`}>
              <span>{m.content}</span>
            </div>
          ))}
        </div>
        <form className="chat-input" onSubmit={send}>
          <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="例如：我想面试 AI 产品经理岗位" />
          <button className="primary-btn" disabled={loading}>
            {loading ? "生成中..." : "发送"}
          </button>
        </form>
      </article>
    </section>
  );
}
