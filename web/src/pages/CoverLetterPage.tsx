import { ChangeEvent, DragEvent, FormEvent, KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";
import { NavLink } from "react-router-dom";
import { callCareerforgeSkill, callCareerforgeSkillMultipart } from "../lib/api";
import { useModelSettings } from "../context/ModelSettingsContext";
import { useCareerFeatureGuard } from "../components/CareerFeatureGuard";

type CoverLetterMode = "pdf" | "conversation";
type Scenario = "email" | "chat";
type Language = "zh" | "en" | "both";
type MessageRole = "user" | "assistant";

type ConversationMessage = {
  id: string;
  role: MessageRole;
  content: string;
  outputText?: string;
  error?: boolean;
};

type HistoryMessage = {
  role: MessageRole;
  content: string;
  output_text?: string;
};

type CoverLetterResponse = {
  reply?: string;
  output_text?: string;
  result?: Record<string, unknown>;
  error?: string;
  message?: string;
};

const SCENARIO_OPTIONS: Array<{ value: Scenario; label: string; description: string }> = [
  { value: "email", label: "邮件求职信", description: "完整求职信" },
  { value: "chat", label: "打招呼短消息", description: "简短有针对性的消息" },
];

const LANGUAGE_OPTIONS: Array<{ value: Language; label: string }> = [
  { value: "zh", label: "中文" },
  { value: "en", label: "英文" },
  { value: "both", label: "中英文" },
];

function createMessageId() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function isPdfFile(file: File) {
  return file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
}

function asString(value: unknown) {
  return typeof value === "string" ? value.trim() : "";
}

export function CoverLetterPage() {
  const { settings } = useModelSettings();
  const featureGuard = useCareerFeatureGuard(settings, "求职信生成");
  const [mode, setMode] = useState<CoverLetterMode>("pdf");
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [jdText, setJdText] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [scenario, setScenario] = useState<Scenario>("email");
  const [language, setLanguage] = useState<Language>("zh");
  const [input, setInput] = useState("");
  const [messagesByMode, setMessagesByMode] = useState<Record<CoverLetterMode, ConversationMessage[]>>({ pdf: [], conversation: [] });
  const messages = messagesByMode[mode];
  const [loadingByMode, setLoadingByMode] = useState<Record<CoverLetterMode, boolean>>({ pdf: false, conversation: false });
  const loading = loadingByMode[mode];
  const [isDragOver, setIsDragOver] = useState(false);
  const [fileError, setFileError] = useState("");
  const [jdError, setJdError] = useState("");
  const [copyTargetId, setCopyTargetId] = useState("");
  const [copyState, setCopyState] = useState<"idle" | "copied" | "error">("idle");
  const [failedMessage, setFailedMessage] = useState("");
  const [failedMessageId, setFailedMessageId] = useState("");
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const logEndRef = useRef<HTMLDivElement | null>(null);

  const history = useMemo<HistoryMessage[]>(
    () => messages.map(({ role, content, outputText }) => ({
      role,
      content,
      ...(outputText ? { output_text: outputText } : {}),
    })),
    [messages]
  );
  const showEmptyState = messages.length === 0 && !loading;
  const showInitialLoadingState = loading && messages.length === 0;

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, loading]);

  const selectResumeFile = (file: File | null) => {
    if (!file) return;
    if (!isPdfFile(file)) {
      setFileError("仅支持 PDF 文件。");
      setResumeFile(null);
      return;
    }
    setFileError("");
    setResumeFile(file);
  };

  const onFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    selectResumeFile(event.target.files?.[0] ?? null);
    event.target.value = "";
  };

  const onDropResume = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setIsDragOver(false);
    selectResumeFile(event.dataTransfer.files?.[0] ?? null);
  };

  const onDropzoneKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      fileInputRef.current?.click();
    }
  };

  const addMessage = (message: Omit<ConversationMessage, "id">) => {
    const id = createMessageId();
    setMessagesByMode((current) => ({ ...current, [mode]: [...(current[mode] ?? []), { id, ...message }] }));
    return id;
  };
  const switchMode = (nextMode: CoverLetterMode) => {
    if (nextMode === mode) return;
    setMode(nextMode);
    setFailedMessage("");
    setFailedMessageId("");
    setCopyTargetId("");
    setCopyState("idle");
  };

  const sendMessage = async (messageOverride?: string, allowEmptyStart = false, fresh = false) => {
    const message = (messageOverride ?? input).trim();
    const canStartWithPdf = mode === "pdf" && Boolean(resumeFile) && (messages.length === 0 || allowEmptyStart || fresh) && !message;
    if (loading || (!message && !canStartWithPdf)) return;

    if (mode === "pdf" && !resumeFile) {
      setFileError("请先上传 PDF 简历，或切换到没有简历模式。");
      return;
    }

    if (!jdText.trim()) {
      setJdError("请先填写岗位信息。");
      return;
    }

    if (fresh) {
      setMessagesByMode((current) => ({ ...current, [mode]: [] }));
      setFailedMessage("");
      setFailedMessageId("");
      setCopyTargetId("");
      setCopyState("idle");
      setFileError("");
    }

    if (message) {
      addMessage({ role: "user", content: message });
      setInput("");
    }
    setLoadingByMode((current) => ({ ...current, [mode]: true }));
    setFailedMessage("");
    setFailedMessageId("");
    setCopyState("idle");

    const effectiveHistory = fresh ? [] : history;
    const payload = {
      message,
      history: JSON.stringify(effectiveHistory),
      jd_text: jdText,
      company_name: companyName,
      scenario,
      language,
      resume_source: mode,
    };

    try {
      const response = mode === "pdf"
        ? await callCareerforgeSkillMultipart<CoverLetterResponse>(
            settings,
            "/careerforge/cover-letter/chat",
            payload,
            { resume: resumeFile }
          )
        : await callCareerforgeSkill<CoverLetterResponse>(settings, "/careerforge/cover-letter/chat", {
            ...payload,
            history: effectiveHistory,
          });
      const result = (response.result ?? {}) as Record<string, unknown>;
      const reply = asString(response.reply) || asString(result.reply);
      const outputText = asString(response.output_text) || asString(result.output_text);
      const errorMessage = asString(response.message) || asString(result.message) || asString(response.error);

      if (errorMessage && !reply && !outputText) {
        const errorId = addMessage({ role: "assistant", content: errorMessage, error: true });
        setFailedMessage(message);
        setFailedMessageId(errorId);
        return;
      }

      if (reply || outputText) {
        addMessage({ role: "assistant", content: reply, outputText });
      }
    } catch (error) {
      const errorMessage = (error as Error).message || "请求失败，请稍后重试。";
      const errorId = addMessage({ role: "assistant", content: errorMessage, error: true });
      setFailedMessage(message);
      setFailedMessageId(errorId);
    } finally {
      setLoadingByMode((current) => ({ ...current, [mode]: false }));
    }
  };

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    void sendMessage();
  };

  const onComposerKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void sendMessage();
    }
  };

  const onCopyOutput = async (messageId: string, outputText: string) => {
    if (!outputText) return;
    setCopyTargetId(messageId);
    try {
      await navigator.clipboard.writeText(outputText);
      setCopyState("copied");
    } catch {
      setCopyState("error");
    }
  };

  const getCopyLabel = (messageId: string) => {
    if (copyTargetId !== messageId) return "复制结果";
    return copyState === "copied" ? "已复制" : copyState === "error" ? "复制失败" : "复制结果";
  };

  return (
    <>
      {featureGuard.overlay}
      <section className="cover-letter-page">
        <div className="cover-letter-workspace">
          <aside className="surface cover-letter-materials" aria-label="求职信材料和偏好">
            <header className="cover-letter-section-head">
              <div>
                <p className="cover-letter-kicker">材料</p>
                <h1>求职信撰写</h1>
              </div>
              <span className="cover-letter-status-dot" aria-label="工作区已就绪" title="工作区已就绪" />
            </header>

            <div className="cover-letter-mode-switch" role="group" aria-label="简历来源">
              <button type="button" className={mode === "pdf" ? "is-active" : ""} aria-pressed={mode === "pdf"} onClick={() => switchMode("pdf")}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                  <path d="M14 2v6h6M8 13h8M8 17h6" />
                </svg>
                <span>已有简历</span>
              </button>
              <button type="button" className={mode === "conversation" ? "is-active" : ""} aria-pressed={mode === "conversation"} onClick={() => switchMode("conversation")}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2" />
                  <circle cx="12" cy="7" r="4" />
                </svg>
                <span>没有简历</span>
              </button>
            </div>

            {mode === "pdf" ? (
              <div className="cover-letter-upload-wrap">
                <div
                  className={`cover-letter-upload${isDragOver ? " is-dragover" : ""}${resumeFile ? " has-file" : ""}`}
                  role="button"
                  tabIndex={0}
                  aria-label="上传 PDF 简历"
                  onClick={() => fileInputRef.current?.click()}
                  onKeyDown={onDropzoneKeyDown}
                  onDragOver={(event) => {
                    event.preventDefault();
                    setIsDragOver(true);
                  }}
                  onDragLeave={() => setIsDragOver(false)}
                  onDrop={onDropResume}
                >
                  <input ref={fileInputRef} className="cover-letter-file-input" type="file" accept=".pdf,application/pdf" onChange={onFileChange} />
                  <span className="cover-letter-upload-icon" aria-hidden="true">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M12 16V4M7 9l5-5 5 5" />
                      <path d="M5 20h14" />
                    </svg>
                  </span>
                  <strong>{resumeFile ? "简历文件已就绪" : "上传简历文件"}</strong>
                  <span>{resumeFile ? resumeFile.name : "点击选择或拖拽到这里"}</span>
                </div>
                {resumeFile ? (
                  <button type="button" className="cover-letter-file-clear" onClick={() => { setResumeFile(null); setFileError(""); }}>
                    移除当前文件
                  </button>
                ) : null}
              </div>
            ) : (
              <div className="cover-letter-conversation-note">
                <span className="cover-letter-note-icon" aria-hidden="true">i</span>
                <p>没有简历也可以开始。把经历、优势和职业方向告诉我，剩下的内容会在对话中逐步补齐。</p>
              </div>
            )}
            {fileError ? <p className="cover-letter-field-error" role="alert">{fileError}</p> : null}

            <label className={`cover-letter-field${jdError ? " is-invalid" : ""}`} htmlFor="cl-jd">
              <span>岗位信息 <em>必填</em></span>
              <textarea id="cl-jd" rows={3} value={jdText} onChange={(event) => { setJdText(event.target.value); if (jdError) setJdError(""); }} placeholder="粘贴目标岗位的职责与任职要求" aria-required="true" />
            </label>
            {jdError ? <p className="cover-letter-field-error" role="alert">{jdError}</p> : null}

            <fieldset className="cover-letter-choice-group">
              <legend>投递场景</legend>
              <div className="cover-letter-segmented">
                {SCENARIO_OPTIONS.map((option) => (
                  <button key={option.value} type="button" className={scenario === option.value ? "is-active" : ""} aria-pressed={scenario === option.value} onClick={() => setScenario(option.value)}>
                    <span>{option.label}</span>
                    <small>{option.description}</small>
                  </button>
                ))}
              </div>
            </fieldset>

            <div className="cover-letter-preference-grid">
              <label className="cover-letter-field" htmlFor="cl-company">
                <span>公司名称 <small>可选</small></span>
                <input id="cl-company" value={companyName} onChange={(event) => setCompanyName(event.target.value)} placeholder="例如：MirrorView" />
              </label>

              <fieldset className="cover-letter-choice-group">
                <legend>输出语言</legend>
                <div className="cover-letter-segmented cover-letter-language-segmented">
                  {LANGUAGE_OPTIONS.map((option) => (
                    <button key={option.value} type="button" className={language === option.value ? "is-active" : ""} aria-pressed={language === option.value} onClick={() => setLanguage(option.value)}>
                      {option.label}
                    </button>
                  ))}
                </div>
              </fieldset>
            </div>

            {mode === "pdf" ? (
              <button type="button" className="primary-btn cover-letter-start-btn" disabled={loading || !resumeFile || !jdText.trim()} onClick={() => void sendMessage("", false, true)}>
                <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="m5 12 14-7-4 14-3-6-7-1Z" />
                  <path d="m12 13 3-3" />
                </svg>
                {loading ? "处理中..." : "开始撰写"}
              </button>
            ) : null}
          </aside>

          <section className="surface cover-letter-chat-panel" aria-label="求职信对话工作区">
            <header className="cover-letter-chat-head">
              <div>
                <p className="cover-letter-kicker">写作区</p>
                <h2>写作对话</h2>
              </div>
              <div className="cover-letter-context-pills" aria-label="当前写作设置">
                <span>{scenario === "email" ? "邮件求职信" : "打招呼短消息"}</span>
                <span>{language === "zh" ? "中文" : language === "en" ? "英文" : "中英文"}</span>
                {resumeFile ? <span>PDF 已连接</span> : null}
              </div>
            </header>

            <div className="cover-letter-chat-log" role="log" aria-live="polite">
              {showInitialLoadingState ? (
                <div className="cover-letter-message assistant is-loading cover-letter-message--loading-start">
                  <div className="cover-letter-message-meta">助手</div>
                  <div className="cover-letter-loading-line"><span /><span /><span /></div>
                </div>
              ) : null}

              {showEmptyState ? (
                <div className="cover-letter-chat-empty">
                  <span className="cover-letter-empty-mark" aria-hidden="true">✦</span>
                  <h3>{mode === "pdf" ? "材料准备好后开始" : "从你的经历开始"}</h3>
                  <p>{mode === "pdf" ? "上传简历并填写岗位信息，助手会根据材料开始写作。" : "在下方输入职业身份、相关经历或想申请的方向。"}</p>
                </div>
              ) : null}

              {messages.map((message) => (
                <div key={message.id} className={`cover-letter-message ${message.role}${message.error ? " is-error" : ""}`}>
                  <div className="cover-letter-message-meta">{message.role === "user" ? "你" : "助手"}</div>
                  {message.content ? <div className="cover-letter-message-text">{message.content}</div> : null}
                  {message.outputText ? (
                    <div className="cover-letter-output-block">
                      <div className="cover-letter-output-head">
                        <span>当前版本</span>
                      </div>
                      <pre>{message.outputText}</pre>
                      <div className="cover-letter-output-foot">
                        <button type="button" className="cover-letter-copy-btn" aria-label={getCopyLabel(message.id)} title={getCopyLabel(message.id)} onClick={() => void onCopyOutput(message.id, message.outputText || "")}>
                          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                            <rect x="9" y="9" width="11" height="11" rx="2" />
                            <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                          </svg>
                        </button>
                      </div>
                    </div>
                  ) : null}
                  {message.error && failedMessageId === message.id ? (
                    <button type="button" className="cover-letter-retry-btn" onClick={() => void sendMessage(failedMessage, failedMessage === "")} disabled={loading}>
                      重试
                    </button>
                  ) : null}
                </div>
              ))}
              {loading && messages.length > 0 ? (
                <div className="cover-letter-message assistant is-loading">
                  <div className="cover-letter-message-meta">助手</div>
                  <div className="cover-letter-loading-line"><span /><span /><span /></div>
                </div>
              ) : null}
              <div ref={logEndRef} />
            </div>

            <form className="cover-letter-composer" onSubmit={onSubmit}>
              <textarea value={input} onChange={(event) => setInput(event.target.value)} onKeyDown={onComposerKeyDown} rows={2} placeholder={mode === "conversation" ? "告诉我你的职业身份、经历或想修改的地方" : "告诉我想如何调整这封信"} aria-label="输入求职信修改或补充内容" />
              <button type="submit" className="primary-btn cover-letter-send-btn" disabled={loading || !input.trim()}>
                <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="m22 2-7 20-4-9-9-4Z" />
                  <path d="M22 2 11 13" />
                </svg>
                发送
              </button>
            </form>
          </section>
        </div>
      </section>
    </>
  );
}
