import { FormEvent, SyntheticEvent, useMemo, useRef, useState } from "react";
import { callCareerforgeSkill } from "../lib/api";
import { useModelSettings } from "../context/ModelSettingsContext";

type Msg = { role: "user" | "assistant"; content: string };

type ResultState = {
  kind: "idle" | "report" | "error";
  reportHtml: string;
  message: string;
};

const TEMPLATE_OPTIONS = [
  { value: "01", label: "01 Editorial 杂志编辑风" },
  { value: "02", label: "02 Minimal 极简主义" },
  { value: "03", label: "03 Sidebar Navy 深蓝双栏" },
  { value: "04", label: "04 Sidebar Dark 深灰左栏" },
  { value: "05", label: "05 Dark Header 深色头部" },
  { value: "06", label: "06 Clean Teal 清新青色" },
  { value: "07", label: "07 Elegant 优雅对称" }
];

const LANGUAGE_OPTIONS = [
  { value: "zh", label: "中文" },
  { value: "en", label: "英文" },
  { value: "both", label: "中英文双版" }
];

const PHOTO_OPTIONS = [
  { value: "no_photo", label: "不放照片" },
  { value: "with_photo", label: "放照片" }
];

const INITIAL_MESSAGE =
  "我们从零开始制作简历。先告诉我目标岗位、你的教育背景、工作或项目经历，以及想重点突出的能力。";

export function ResumeCraftPage() {
  const { settings } = useModelSettings();
  const [messages, setMessages] = useState<Msg[]>([{ role: "assistant", content: INITIAL_MESSAGE }]);
  const [input, setInput] = useState("");
  const [templateCode, setTemplateCode] = useState("02");
  const [language, setLanguage] = useState("zh");
  const [photoPref, setPhotoPref] = useState("no_photo");
  const [chatLoading, setChatLoading] = useState(false);
  const [renderLoading, setRenderLoading] = useState(false);
  const [result, setResult] = useState<ResultState>({ kind: "idle", reportHtml: "", message: "" });
  const [reportName, setReportName] = useState("resume-craft-report.html");
  const [frameHeight, setFrameHeight] = useState(980);
  const previewFrameRef = useRef<HTMLIFrameElement | null>(null);

  const hasUserMessages = useMemo(() => messages.some((msg) => msg.role === "user"), [messages]);

  const onSend = async (e: FormEvent) => {
    e.preventDefault();
    const text = input.trim();
    if (!text || chatLoading || renderLoading) {
      return;
    }

    const history = messages.map((msg) => ({ role: msg.role, content: msg.content }));
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setInput("");
    setChatLoading(true);
    try {
      const resp = await callCareerforgeSkill(settings, "/careerforge/resume-craft/chat-turn", {
        message: text,
        history,
        template_code: templateCode,
        language,
        photo_pref: photoPref
      });
      const reply =
        (typeof resp.reply === "string" && resp.reply.trim()) ||
        (typeof resp.message === "string" && resp.message.trim()) ||
        "我已收到你的信息，请继续补充经历细节。";
      setMessages((prev) => [...prev, { role: "assistant", content: reply }]);
    } catch (err) {
      setMessages((prev) => [...prev, { role: "assistant", content: (err as Error).message }]);
    } finally {
      setChatLoading(false);
    }
  };

  const onRenderResume = async () => {
    if (!hasUserMessages || chatLoading || renderLoading) {
      return;
    }
    setRenderLoading(true);
    try {
      const resp = await callCareerforgeSkill(settings, "/careerforge/resume-craft/render", {
        history: messages.map((msg) => ({ role: msg.role, content: msg.content })),
        template_code: templateCode,
        language,
        photo_pref: photoPref
      });
      const html =
        (typeof (resp as Record<string, unknown>).report_html === "string" &&
          ((resp as Record<string, unknown>).report_html as string)) ||
        "";
      const name =
        (typeof (resp as Record<string, unknown>).report_name === "string" &&
          ((resp as Record<string, unknown>).report_name as string)) ||
        "resume-craft-report.html";

      if (!html.trim()) {
        setResult({ kind: "error", reportHtml: "", message: "未生成有效 HTML，请继续补充信息后重试。" });
      } else {
        setReportName(name);
        setResult({ kind: "report", reportHtml: html, message: "" });
      }
    } catch (err) {
      setResult({ kind: "error", reportHtml: "", message: (err as Error).message });
    } finally {
      setRenderLoading(false);
    }
  };

  const onPreviewLoad = (e: SyntheticEvent<HTMLIFrameElement>) => {
    try {
      const frame = e.currentTarget;
      const doc = frame.contentDocument;
      if (!doc) {
        return;
      }
      const bodyHeight = doc.body?.scrollHeight ?? 0;
      const htmlHeight = doc.documentElement?.scrollHeight ?? 0;
      const next = Math.max(720, bodyHeight, htmlHeight);
      setFrameHeight(next + 12);
    } catch {
      setFrameHeight(980);
    }
  };

  const exportHtml = () => {
    if (result.kind !== "report" || !result.reportHtml.trim()) {
      return;
    }
    const blob = new Blob([result.reportHtml], { type: "text/html;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = reportName || "resume-craft-report.html";
    link.click();
    URL.revokeObjectURL(url);
  };

  const exportPdf = () => {
    const frameWindow = previewFrameRef.current?.contentWindow;
    if (!frameWindow) {
      return;
    }
    frameWindow.focus();
    frameWindow.print();
  };

  return (
    <section className="resume-craft-page">
      <div className="resume-craft-layout">
        <article className="surface resume-craft-chat-panel">
          <header className="resume-craft-head">
            <div className="resume-craft-head-copy">
              <h2>Resume Craft Agent</h2>
              <p>通过多轮对话收集信息，从零生成简历。</p>
            </div>
            <div className="resume-craft-controls">
              <label className="resume-craft-control">
                <span>模板</span>
                <select value={templateCode} onChange={(e) => setTemplateCode(e.target.value)}>
                  {TEMPLATE_OPTIONS.map((item) => (
                    <option key={item.value} value={item.value}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="resume-craft-control">
                <span>语言</span>
                <select value={language} onChange={(e) => setLanguage(e.target.value)}>
                  {LANGUAGE_OPTIONS.map((item) => (
                    <option key={item.value} value={item.value}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="resume-craft-control">
                <span>照片</span>
                <select value={photoPref} onChange={(e) => setPhotoPref(e.target.value)}>
                  {PHOTO_OPTIONS.map((item) => (
                    <option key={item.value} value={item.value}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <button className="primary-btn resume-craft-render-btn" onClick={onRenderResume} disabled={!hasUserMessages || chatLoading || renderLoading}>
              {renderLoading ? "生成中..." : "生成简历"}
            </button>
          </header>

          <div className="chat-log resume-craft-chat-log">
            {messages.map((msg, idx) => (
              <div key={`${msg.role}-${idx}`} className={`msg ${msg.role}`}>
                <span>{msg.content}</span>
              </div>
            ))}
            {chatLoading ? (
              <div className="msg assistant">
                <span>正在思考，请稍候...</span>
              </div>
            ) : null}
          </div>

          <form className="chat-input resume-craft-chat-input" onSubmit={onSend}>
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="例如：目标岗位是 AI 应用开发，我有 2 年后端与 RAG 项目经验"
            />
            <button className="primary-btn" disabled={!input.trim() || chatLoading || renderLoading}>
              {chatLoading ? "发送中..." : "发送"}
            </button>
          </form>
        </article>

        <section className="resume-craft-output">
          {result.kind === "idle" ? <p className="muted">对话完成后点击“生成简历”，预览会展示在这里。</p> : null}
          {result.kind === "error" ? <p className="resume-result-error">{result.message}</p> : null}
          {result.kind === "report" ? (
            <>
              <header className="resume-craft-preview-head">
                <h3>简历预览</h3>
                <span>已嵌入当前页面</span>
              </header>
              <iframe
                ref={previewFrameRef}
                title="Resume Craft HTML Preview"
                className="resume-craft-preview-frame"
                srcDoc={result.reportHtml}
                onLoad={onPreviewLoad}
                style={{ height: `${frameHeight}px` }}
              />
              <div className="resume-craft-actions">
                <button type="button" className="ghost-btn" onClick={exportHtml}>
                  导出 HTML
                </button>
                <button type="button" className="ghost-btn" onClick={exportPdf}>
                  导出 PDF
                </button>
              </div>
            </>
          ) : null}
        </section>
      </div>
    </section>
  );
}
