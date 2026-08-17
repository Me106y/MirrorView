import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { callCareerforgeSkill, callMockInterviewReport } from "../lib/api";
import { useModelSettings } from "../context/ModelSettingsContext";
import { useCareerFeatureGuard } from "../components/CareerFeatureGuard";
import type {
  MockInterviewActionItem,
  MockInterviewConversationMessage,
  MockInterviewLanguage,
  MockInterviewQuestionBankItem,
  MockInterviewReport,
  MockInterviewRound,
  MockInterviewScope,
  MockInterviewSession,
  MockInterviewSetup,
} from "../types";

const LANGUAGE_OPTIONS: Array<{ value: MockInterviewLanguage; label: string; description: string }> = [
  { value: "zh", label: "中文", description: "更贴近日常求职语境" },
  { value: "en", label: "英文", description: "适合外企或英文轮训练" },
];

const SCOPE_OPTIONS: Array<{ value: MockInterviewScope; label: string; description: string; eta: string }> = [
  { value: "full", label: "完整三轮", description: "HR → 业务主管 → 终面", eta: "约 30–45 分钟" },
  { value: "hr", label: "只练 HR 面", description: "动机、稳定性、文化匹配", eta: "约 8–12 分钟" },
  { value: "business", label: "只练业务面", description: "深挖项目、能力与取舍", eta: "约 12–18 分钟" },
  { value: "executive", label: "只练终面", description: "思维方式、成长潜力、大局观", eta: "约 8–12 分钟" },
  { value: "focused", label: "专项训练", description: "围绕一个高频薄弱点集中练习", eta: "约 10–15 分钟" },
];

const ROUND_TRACK = [
  { key: "hr", title: "HR 面", subtitle: "动机 / 文化匹配 / 稳定性" },
  { key: "business", title: "业务主管面", subtitle: "项目深挖 / 专业能力 / 压力追问" },
  { key: "executive", title: "终面", subtitle: "成长潜力 / 战略视角 / 复盘能力" },
];

const QUICK_ACTIONS = [
  { key: "skip", label: "跳过当前问题", prompt: "跳过当前问题，继续下一题。" },
  { key: "pause", label: "暂停面试", prompt: "暂停面试。请确认已暂停，并等待我说继续。" },
  { key: "resume", label: "继续面试", prompt: "继续面试，请根据已有上下文接着提问。" },
] as const;

const INITIAL_SETUP: MockInterviewSetup = {
  targetRole: "",
  jdText: "",
  resumeText: "",
  companyName: "",
  language: "zh",
  scope: "full",
  focusTopic: "",
};

const INITIAL_SESSION: MockInterviewSession = {
  stage: "setup",
  setup: INITIAL_SETUP,
  messages: [],
  startedAt: "",
  busy: false,
  errorMessage: "",
  report: null,
};

function createId() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function formatTime(iso: string) {
  if (!iso) return "";
  const date = new Date(iso);
  return new Intl.DateTimeFormat("zh-CN", { hour: "2-digit", minute: "2-digit" }).format(date);
}

function languageLabel(language: MockInterviewLanguage) {
  return language === "en" ? "英文" : "中文";
}

function scopeLabel(scope: MockInterviewScope) {
  return SCOPE_OPTIONS.find((item) => item.value === scope)?.label || "完整三轮";
}

function scoreTone(score: number) {
  if (score >= 8) return "good";
  if (score >= 6) return "mid";
  return "weak";
}

function buildHistory(messages: MockInterviewConversationMessage[]) {
  return messages
    .filter((item) => item.content.trim())
    .map((item) => ({ role: item.role, content: item.content }));
}

function buildStartPrompt(setup: MockInterviewSetup) {
  const scopeText = {
    full: "完整三轮模拟面试",
    hr: "只进行 HR 面试训练",
    business: "只进行业务主管面试训练",
    executive: "只进行终面 / 高管面试训练",
    focused: `专项训练：${setup.focusTopic || "项目经历深挖"}`,
  }[setup.scope];

  return [
    "现在开始一场新的文字版模拟面试。",
    `目标岗位：${setup.targetRole}`,
    `面试语言：${setup.language === "en" ? "English" : "Chinese"}`,
    `训练范围：${scopeText}`,
    setup.companyName ? `目标公司：${setup.companyName}` : "",
    "岗位 JD：",
    setup.jdText,
    "候选人简历：",
    setup.resumeText,
    "请严格按照 mock-interview 的规则进行：先用一句话说明面试已开始，再提出第一题。只输出面试官当前这一轮的话术，不要输出报告。",
  ]
    .filter(Boolean)
    .join("\n\n");
}

function buildEmptyReportFallback(setup: MockInterviewSetup): MockInterviewReport {
  return {
    candidateName: "候选人",
    targetRole: setup.targetRole,
    companyName: setup.companyName,
    language: setup.language,
    scope: setup.scope,
    overallScore: 71,
    hireRecommendation: "待定，需要继续打磨",
    summary: "当前报告暂未完整生成，建议稍后重试。",
    dimensions: [],
    rounds: [],
    questionBank: [],
    actionItems: [],
  };
}

export function MockInterviewPage() {
  const { settings } = useModelSettings();
  const featureGuard = useCareerFeatureGuard(settings, "模拟面试");
  const [session, setSession] = useState<MockInterviewSession>(INITIAL_SESSION);
  const [input, setInput] = useState("");
  const [formErrors, setFormErrors] = useState<Record<string, string>>({});
  const [showTranscript, setShowTranscript] = useState(false);
  const logEndRef = useRef<HTMLDivElement | null>(null);

  const activeMessages = session.messages;
  const currentScope = useMemo(() => SCOPE_OPTIONS.find((item) => item.value === session.setup.scope), [session.setup.scope]);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [activeMessages, session.stage, session.busy]);

  const patchSession = (patch: Partial<MockInterviewSession>) => {
    setSession((current) => ({ ...current, ...patch }));
  };

  const patchMessage = (id: string, patch: Partial<MockInterviewConversationMessage>) => {
    setSession((current) => ({
      ...current,
      messages: current.messages.map((item) => (item.id === id ? { ...item, ...patch } : item)),
    }));
  };

  const appendMessage = (message: Omit<MockInterviewConversationMessage, "id">) => {
    const id = createId();
    setSession((current) => ({
      ...current,
      messages: [...current.messages, { id, ...message }],
    }));
    return id;
  };

  const validateSetup = () => {
    const nextErrors: Record<string, string> = {};
    if (!session.setup.targetRole.trim()) nextErrors.targetRole = "请填写目标岗位。";
    if (!session.setup.jdText.trim()) nextErrors.jdText = "请粘贴目标岗位 JD。";
    if (!session.setup.resumeText.trim()) nextErrors.resumeText = "请粘贴简历内容或经历摘要。";
    if (session.setup.scope === "focused" && !session.setup.focusTopic.trim()) {
      nextErrors.focusTopic = "请选择专项训练方向。";
    }
    setFormErrors(nextErrors);
    return Object.keys(nextErrors).length === 0;
  };

  const streamAssistantMessage = async (id: string, content: string) => {
    const chunkSize = 18;
    for (let index = chunkSize; index <= content.length + chunkSize; index += chunkSize) {
      await new Promise((resolve) => setTimeout(resolve, 18));
      patchMessage(id, {
        content: content.slice(0, Math.min(index, content.length)),
        status: Math.min(index, content.length) >= content.length ? "sent" : "streaming",
      });
    }
  };

  const sendTurn = async (message: string, options?: { displayUserMessage?: boolean; resetMessages?: boolean }) => {
    if (session.busy || featureGuard.blocked) return;
    const text = message.trim();
    if (!text) return;

    const shouldDisplayUserMessage = options?.displayUserMessage ?? true;
    const baseMessages = options?.resetMessages ? [] : session.messages;
    const userMessage: MockInterviewConversationMessage | null = shouldDisplayUserMessage
      ? {
          id: createId(),
          role: "user",
          content: text,
          createdAt: new Date().toISOString(),
          status: "sent",
        }
      : null;

    const assistantId = createId();
    const assistantPlaceholder: MockInterviewConversationMessage = {
      id: assistantId,
      role: "assistant",
      content: "",
      createdAt: new Date().toISOString(),
      status: "streaming",
    };

    setSession((current) => ({
      ...current,
      stage: "active",
      busy: true,
      errorMessage: "",
      startedAt: current.startedAt || new Date().toISOString(),
      report: options?.resetMessages ? null : current.report,
      messages: [...baseMessages, ...(userMessage ? [userMessage] : []), assistantPlaceholder],
    }));

    try {
      const history = buildHistory([...(baseMessages || []), ...(userMessage ? [userMessage] : [])]);
      const response = await callCareerforgeSkill<{ mode?: string; language?: string; target_role?: string }>(
        settings,
        "/careerforge/agent/chat",
        {
          message: text,
          history,
          conversation_mode: "mock_interview",
          setup: session.setup,
        }
      );
      const answer = (response.reply || "系统暂未返回内容，请稍后重试。").trim();
      await streamAssistantMessage(assistantId, answer);
      setSession((current) => ({ ...current, busy: false, errorMessage: "" }));
    } catch (error) {
      const messageText = (error as Error).message || "请求失败，请稍后重试。";
      patchMessage(assistantId, { content: `${messageText}\n\n请稍后重试。`, status: "error" });
      setSession((current) => ({ ...current, stage: "error", busy: false, errorMessage: messageText }));
    }
  };

  const startInterview = async () => {
    if (!validateSetup()) return;
    const startPrompt = buildStartPrompt(session.setup);
    setShowTranscript(false);
    await sendTurn(startPrompt, { displayUserMessage: false, resetMessages: true });
  };

  const submitReply = async (event?: FormEvent) => {
    event?.preventDefault();
    const text = input.trim();
    if (!text || session.busy) return;
    setInput("");
    await sendTurn(text);
  };

  const finishInterview = async () => {
    if (session.busy || session.messages.length === 0) return;
    patchSession({ stage: "reporting", busy: true, errorMessage: "" });
    try {
      const response = await callMockInterviewReport<MockInterviewReport>(settings, {
        setup: session.setup,
        history: buildHistory(session.messages),
      });
      const report = response.result || buildEmptyReportFallback(session.setup);
      setSession((current) => ({
        ...current,
        stage: "completed",
        busy: false,
        errorMessage: "",
        report,
      }));
    } catch (error) {
      setSession((current) => ({
        ...current,
        stage: "error",
        busy: false,
        errorMessage: (error as Error).message || "生成报告失败，请稍后重试。",
      }));
    }
  };

  const restartInterview = () => {
    setInput("");
    setFormErrors({});
    setShowTranscript(false);
    setSession(INITIAL_SESSION);
  };

  const openHtmlReport = () => {
    const html = session.report?.htmlReport?.trim();
    if (!html) return;
    const blob = new Blob([html], { type: "text/html;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    window.open(url, "_blank", "noopener,noreferrer");
    window.setTimeout(() => URL.revokeObjectURL(url), 30_000);
  };

  const updateSetup = <K extends keyof MockInterviewSetup>(key: K, value: MockInterviewSetup[K]) => {
    setSession((current) => ({
      ...current,
      setup: {
        ...current.setup,
        [key]: value,
      },
    }));
    setFormErrors((current) => ({ ...current, [key]: "" }));
  };

  const renderSetup = () => (
    <section className="mock-interview-page mock-interview-page--setup">
      <div className="mock-interview-setup-grid">
        <article className="surface mock-interview-panel mock-interview-panel--form">
          <div className="mock-interview-panel-head">
            <div>
              <p className="mock-interview-kicker">Mock Interview Workspace</p>
              <h1>开始一场更像真实现场的文字面试</h1>
              <p>先整理岗位、JD 和简历信息，再进入逐题问答。当前版本聚焦文字面试，不包含旁听或视频链路。</p>
            </div>
            <span className="mock-interview-status-chip">{currentScope?.eta}</span>
          </div>

          <div className="mock-interview-form-grid">
            <label className="mock-interview-field">
              <span>目标岗位</span>
              <input
                value={session.setup.targetRole}
                onChange={(event) => updateSetup("targetRole", event.target.value)}
                placeholder="例如：AI 产品经理"
              />
              {formErrors.targetRole ? <em>{formErrors.targetRole}</em> : null}
            </label>

            <label className="mock-interview-field">
              <span>目标公司（可选）</span>
              <input
                value={session.setup.companyName}
                onChange={(event) => updateSetup("companyName", event.target.value)}
                placeholder="例如：字节跳动 / 月之暗面"
              />
            </label>

            <label className="mock-interview-field mock-interview-field--full">
              <span>岗位 JD</span>
              <textarea
                value={session.setup.jdText}
                onChange={(event) => updateSetup("jdText", event.target.value)}
                placeholder="粘贴岗位职责、任职要求、加分项等内容"
              />
              {formErrors.jdText ? <em>{formErrors.jdText}</em> : <small>建议保留岗位目标、能力要求与业务上下文，AI 会据此生成更贴近真实场景的问题。</small>}
            </label>

            <label className="mock-interview-field mock-interview-field--full">
              <span>简历文本 / 经历摘要</span>
              <textarea
                value={session.setup.resumeText}
                onChange={(event) => updateSetup("resumeText", event.target.value)}
                placeholder="粘贴简历全文，或至少提供核心项目、职责、成果与转岗背景"
              />
              {formErrors.resumeText ? <em>{formErrors.resumeText}</em> : <small>当前页面先使用文本输入。后续可再接已有简历资产做自动预填。</small>}
            </label>
          </div>

          <div className="mock-interview-option-row">
            <div className="mock-interview-toggle-group" role="radiogroup" aria-label="面试语言">
              <strong>面试语言</strong>
              <div>
                {LANGUAGE_OPTIONS.map((option) => (
                  <button
                    key={option.value}
                    type="button"
                    className={`mock-interview-toggle${session.setup.language === option.value ? " is-active" : ""}`}
                    onClick={() => updateSetup("language", option.value)}
                  >
                    <span>{option.label}</span>
                    <small>{option.description}</small>
                  </button>
                ))}
              </div>
            </div>

            <div className="mock-interview-toggle-group" role="radiogroup" aria-label="面试范围">
              <strong>训练范围</strong>
              <div className="mock-interview-scope-grid">
                {SCOPE_OPTIONS.map((option) => (
                  <button
                    key={option.value}
                    type="button"
                    className={`mock-interview-toggle mock-interview-toggle--scope${session.setup.scope === option.value ? " is-active" : ""}`}
                    onClick={() => updateSetup("scope", option.value)}
                  >
                    <span>{option.label}</span>
                    <small>{option.description}</small>
                    <b>{option.eta}</b>
                  </button>
                ))}
              </div>
            </div>
          </div>

          {session.setup.scope === "focused" ? (
            <label className="mock-interview-field mock-interview-field--full">
              <span>专项训练方向</span>
              <input
                value={session.setup.focusTopic}
                onChange={(event) => updateSetup("focusTopic", event.target.value)}
                placeholder="例如：项目经历深挖 / 英文自我介绍 / 压力面应对"
              />
              {formErrors.focusTopic ? <em>{formErrors.focusTopic}</em> : <small>写得越具体，专项追问越集中。</small>}
            </label>
          ) : null}
        </article>

        <aside className="surface mock-interview-panel mock-interview-panel--brief">
          <div className="mock-interview-brief-head">
            <p className="mock-interview-kicker">本次训练说明</p>
            <h2>{scopeLabel(session.setup.scope)}</h2>
            <p>AI 会根据你的回答自然追问，不在途中打断给反馈。结束后统一输出结构化复盘报告。</p>
          </div>

          <div className="mock-interview-track">
            {ROUND_TRACK.map((item, index) => (
              <article key={item.key} className={`mock-interview-track-item${session.setup.scope !== "full" && session.setup.scope !== item.key ? " is-muted" : ""}`}>
                <span>{index + 1}</span>
                <div>
                  <h3>{item.title}</h3>
                  <p>{item.subtitle}</p>
                </div>
              </article>
            ))}
          </div>

          <div className="mock-interview-rule-list">
            <h3>规则与快捷操作</h3>
            <ul>
              <li>一题一题问答，必要时会继续深挖同一题。</li>
              <li>面试过程中不即时点评，保证更接近真实场景。</li>
              <li>可以随时使用：跳过、暂停、继续、结束并生成报告。</li>
              <li>当前轮次由 AI 根据上下文自动推进，前端不强行猜测。</li>
            </ul>
          </div>

          <button type="button" className="primary-btn mock-interview-start-btn" onClick={startInterview} disabled={featureGuard.blocked || session.busy}>
            开始模拟面试
          </button>
        </aside>
      </div>
    </section>
  );

  const renderActive = () => (
    <section className="mock-interview-page mock-interview-page--active">
      <div className="mock-interview-workspace">
        <aside className="surface mock-interview-sidebar">
          <div className="mock-interview-sidebar-head">
            <p className="mock-interview-kicker">Interview Status</p>
            <h1>{session.setup.targetRole || "模拟面试"}</h1>
            <p>{languageLabel(session.setup.language)} · {scopeLabel(session.setup.scope)} · AI 将依据回答自动推进轮次</p>
          </div>

          <div className="mock-interview-meta-card">
            <span>岗位</span>
            <strong>{session.setup.targetRole || "未填写"}</strong>
            <span>公司</span>
            <strong>{session.setup.companyName || "未指定"}</strong>
            <span>开始时间</span>
            <strong>{session.startedAt ? formatTime(session.startedAt) : "刚刚"}</strong>
          </div>

          <div className="mock-interview-track mock-interview-track--stacked">
            {ROUND_TRACK.map((item, index) => (
              <article key={item.key} className={`mock-interview-track-item${session.setup.scope !== "full" && session.setup.scope !== item.key ? " is-muted" : ""}`}>
                <span>{index + 1}</span>
                <div>
                  <h3>{item.title}</h3>
                  <p>{item.subtitle}</p>
                </div>
              </article>
            ))}
          </div>

          <div className="mock-interview-sidebar-section">
            <h2>快捷操作</h2>
            <div className="mock-interview-action-list">
              {QUICK_ACTIONS.map((action) => (
                <button key={action.key} type="button" className="ghost-btn mock-interview-action-btn" disabled={session.busy} onClick={() => void sendTurn(action.prompt, { displayUserMessage: false })}>
                  {action.label}
                </button>
              ))}
              <button type="button" className="primary-btn mock-interview-action-btn mock-interview-action-btn--finish" disabled={session.busy || !session.messages.length} onClick={finishInterview}>
                结束并生成报告
              </button>
            </div>
          </div>
        </aside>

        <article className="surface mock-interview-chat-panel">
          <div className="mock-interview-chat-head">
            <div>
              <p className="mock-interview-kicker">Live Transcript</p>
              <h2>逐题问答</h2>
              <p>继续像真实面试一样作答，必要时可用快捷操作控制节奏。</p>
            </div>
            <span className={`mock-interview-presence${session.busy ? " is-busy" : ""}`}>{session.busy ? "AI 正在追问…" : "等待你的回答"}</span>
          </div>

          <div className="mock-interview-chat-log" role="log" aria-live="polite">
            {activeMessages.length === 0 ? (
              <div className="mock-interview-empty-state">
                <span>🎙️</span>
                <h3>面试会从第一题开始</h3>
                <p>系统会先给出开场提示与第一题，然后按你的回答继续追问。</p>
              </div>
            ) : null}

            {activeMessages.map((message) => (
              <article key={message.id} className={`mock-interview-message ${message.role}${message.status === "error" ? " is-error" : ""}`}>
                <div className="mock-interview-message-meta">
                  <strong>{message.role === "assistant" ? "面试官" : "你"}</strong>
                  <span>{formatTime(message.createdAt)}</span>
                </div>
                <div className="mock-interview-message-bubble">{message.content || <span className="mock-interview-loading-dots"><i/><i/><i/></span>}</div>
              </article>
            ))}
            <div ref={logEndRef} />
          </div>

          <form className="mock-interview-composer" onSubmit={submitReply}>
            <textarea
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder="输入你的回答，例如用 STAR 结构回答，或直接提出反问。"
              aria-label="输入回答"
            />
            <button type="submit" className="primary-btn mock-interview-send-btn" disabled={session.busy || !input.trim()}>
              {session.busy ? "生成中…" : "发送回答"}
            </button>
          </form>

          {session.errorMessage ? <p className="mock-interview-error-note">{session.errorMessage}</p> : null}
        </article>
      </div>
    </section>
  );

  const renderRounds = (rounds: MockInterviewRound[]) => (
    <div className="mock-interview-round-list">
      {rounds.map((round) => (
        <article key={round.key} className="mock-interview-report-round">
          <header>
            <div>
              <h3>{round.label}</h3>
              <p>{round.summary}</p>
            </div>
            <span className={`mock-interview-score-chip tone-${scoreTone(round.score)}`}>{round.score}/10</span>
          </header>

          <div className="mock-interview-question-list">
            {round.questions.length === 0 ? <p className="mock-interview-muted">该轮在本次会话中未完整展开。</p> : null}
            {round.questions.map((question, index) => (
              <article key={`${round.key}-${index}`} className="mock-interview-question-card">
                <div className="mock-interview-question-row">
                  <span className="mock-interview-question-index">{index + 1}</span>
                  <div>
                    <h4>{question.question}</h4>
                    <p className="mock-interview-question-summary">{question.answerSummary}</p>
                  </div>
                  <span className={`mock-interview-score-chip tone-${scoreTone(question.score)}`}>{question.score}/10</span>
                </div>

                <div className="mock-interview-feedback-grid">
                  <section className="mock-interview-feedback-card tone-good">
                    <strong>优点</strong>
                    <p>{question.strength}</p>
                  </section>
                  <section className="mock-interview-feedback-card tone-weak">
                    <strong>不足</strong>
                    <p>{question.gap}</p>
                  </section>
                  <section className="mock-interview-feedback-card tone-info">
                    <strong>优化建议</strong>
                    <p>{question.suggestion}</p>
                  </section>
                </div>

                <div className="mock-interview-sample-answer">
                  <strong>参考回答方向</strong>
                  <p>{question.sampleAnswer}</p>
                </div>
              </article>
            ))}
          </div>
        </article>
      ))}
    </div>
  );

  const renderQuestionBank = (items: MockInterviewQuestionBankItem[]) => (
    <div className="mock-interview-table-wrap">
      <table className="mock-interview-table">
        <thead>
          <tr>
            <th>轮次</th>
            <th>题目</th>
            <th>核心考察点</th>
            <th>评分</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item, index) => (
            <tr key={`${item.round}-${index}`}>
              <td>{item.round}</td>
              <td>{item.question}</td>
              <td>{item.focus}</td>
              <td>{item.score}/10</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );

  const renderActions = (items: MockInterviewActionItem[]) => (
    <div className="mock-interview-action-cards">
      {items.map((item, index) => (
        <article key={`${item.title}-${index}`} className="mock-interview-action-card">
          <span>{index + 1}</span>
          <div>
            <h3>{item.title}</h3>
            <p>{item.details}</p>
          </div>
        </article>
      ))}
    </div>
  );

  const renderCompleted = () => {
    const report = session.report || buildEmptyReportFallback(session.setup);
    return (
      <section className="mock-interview-page mock-interview-page--report">
        <article className="surface mock-interview-report-shell">
          <div className="mock-interview-report-hero">
            <div>
              <p className="mock-interview-kicker">Report Ready</p>
              <h1>模拟面试结果摘要</h1>
              <p>{report.summary}</p>
            </div>
            <div className="mock-interview-report-actions">
              <button type="button" className="ghost-btn" onClick={() => setShowTranscript((value) => !value)}>
                {showTranscript ? "收起完整对话" : "查看完整对话"}
              </button>
              <button type="button" className="ghost-btn" onClick={openHtmlReport} disabled={!report.htmlReport}>
                打开 HTML 报告
              </button>
              <button type="button" className="primary-btn" onClick={restartInterview}>
                重新开始
              </button>
            </div>
          </div>

          <div className="mock-interview-report-summary">
            <div className="mock-interview-score-ring" aria-label={`综合评分 ${report.overallScore} 分`}>
              <svg viewBox="0 0 120 120" aria-hidden="true">
                <circle cx="60" cy="60" r="54" className="mock-interview-score-ring-track" />
                <circle
                  cx="60"
                  cy="60"
                  r="54"
                  className="mock-interview-score-ring-fill"
                  style={{ strokeDashoffset: 339.292 - (339.292 * Math.max(0, Math.min(100, report.overallScore))) / 100 }}
                />
              </svg>
              <div>
                <strong>{report.overallScore}</strong>
                <span>/ 100</span>
              </div>
            </div>

            <div className="mock-interview-report-copy">
              <span className={`mock-interview-recommendation tone-${report.overallScore >= 75 ? "good" : report.overallScore >= 60 ? "mid" : "weak"}`}>{report.hireRecommendation}</span>
              <dl>
                <div>
                  <dt>目标岗位</dt>
                  <dd>{report.targetRole}</dd>
                </div>
                <div>
                  <dt>公司</dt>
                  <dd>{report.companyName || "未指定"}</dd>
                </div>
                <div>
                  <dt>语言</dt>
                  <dd>{languageLabel(report.language)}</dd>
                </div>
                <div>
                  <dt>训练范围</dt>
                  <dd>{scopeLabel(report.scope)}</dd>
                </div>
              </dl>
            </div>
          </div>

          <section className="mock-interview-report-section">
            <h2>能力维度</h2>
            <div className="mock-interview-dimension-grid">
              {report.dimensions.map((dimension) => (
                <article key={dimension.key} className="mock-interview-dimension-card">
                  <header>
                    <h3>{dimension.label}</h3>
                    <strong className={`tone-${scoreTone(dimension.score)}`}>{dimension.score}/10</strong>
                  </header>
                  <div className="mock-interview-meter"><span className={`tone-${scoreTone(dimension.score)}`} style={{ width: `${dimension.score * 10}%` }} /></div>
                  <p>{dimension.comment}</p>
                </article>
              ))}
            </div>
          </section>

          <section className="mock-interview-report-section">
            <h2>逐轮反馈</h2>
            {renderRounds(report.rounds)}
          </section>

          <section className="mock-interview-report-section">
            <h2>面试题目合集</h2>
            {renderQuestionBank(report.questionBank)}
          </section>

          <section className="mock-interview-report-section">
            <h2>备考行动清单</h2>
            {renderActions(report.actionItems)}
          </section>

          {showTranscript ? (
            <section className="mock-interview-report-section">
              <h2>完整对话</h2>
              <div className="mock-interview-transcript">
                {session.messages.map((message) => (
                  <article key={message.id} className={`mock-interview-transcript-item ${message.role}`}>
                    <strong>{message.role === "assistant" ? "面试官" : "你"}</strong>
                    <p>{message.content}</p>
                  </article>
                ))}
              </div>
            </section>
          ) : null}
        </article>
      </section>
    );
  };

  return (
    <>
      {featureGuard.overlay}
      {session.stage === "setup" ? renderSetup() : null}
      {session.stage === "active" || session.stage === "error" ? renderActive() : null}
      {session.stage === "reporting" ? (
        <section className="mock-interview-page mock-interview-page--loading">
          <article className="surface mock-interview-report-loading">
            <p className="mock-interview-kicker">Generating Report</p>
            <h1>正在整理面试报告</h1>
            <p>AI 正在汇总逐题表现、六维评分与备考建议，请稍候。</p>
            <div className="mock-interview-loading-dots mock-interview-loading-dots--large"><i/><i/><i/></div>
          </article>
        </section>
      ) : null}
      {session.stage === "completed" ? renderCompleted() : null}
    </>
  );
}
