import { ChangeEvent, DragEvent, FormEvent, KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";
import { callCareerforgeSkill, callCareerforgeSkillMultipart } from "../lib/api";
import { useModelSettings } from "../context/ModelSettingsContext";
import { useCareerFeatureGuard } from "../components/CareerFeatureGuard";

type JobHuntMode = "pdf" | "conversation";

interface TopJob {
  title?: string;
  company?: string;
  location?: string;
  salary?: string;
  match_level?: string;
  match_reason?: string;
  url?: string;
}

interface JobHuntResult {
  summary?: string;
  search_strategy?: string[];
  top_jobs?: TopJob[];
  next_actions?: string[];
  assumptions?: string[];
}

type ReportState =
  | { kind: "idle" }
  | { kind: "report"; result: JobHuntResult }
  | { kind: "error"; message: string };

const REGION_OPTIONS = ["中国大陆", "澳大利亚", "新西兰", "美国", "加拿大", "英国", "欧洲", "日本", "韩国", "新加坡", "东南亚", "其他"];
const REQUIREMENT_OPTIONS = ["外企", "国企", "民企", "大厂", "创业公司", "双休", "弹性工作", "远程办公", "签证担保"];
const GLOBAL_PLATFORM_OPTIONS = ["LinkedIn", "Indeed", "Google Jobs", "Glassdoor"];
const REGION_PLATFORM_OPTIONS: Record<string, string[]> = {
  中国大陆: ["Boss直聘", "猎聘", "拉勾", "智联招聘", "前程无忧", "牛客网内推帖", "V2EX 招聘帖", "微信公众号招聘"],
  澳大利亚: ["Seek Australia", "Jora", "Indeed Australia", "Facebook Jobs / Groups"],
  新西兰: ["Seek New Zealand", "Trade Me Jobs", "Indeed New Zealand"],
  美国: ["ZipRecruiter", "Monster", "Dice", "USAJobs", "Wellfound"],
  加拿大: ["ZipRecruiter", "Monster", "Dice", "Job Bank", "Workopolis", "Wellfound"],
  英国: ["Reed", "Totaljobs", "CV-Library", "Indeed UK"],
  欧洲: ["StepStone", "XING"],
  日本: ["Daijob", "GaijinPot Jobs", "Rikunabi"],
  韩国: ["Saramin", "JobKorea", "WorkNet", "People'n Job"],
  新加坡: ["MyCareersFuture", "JobStreet Singapore"],
  东南亚: ["JobStreet", "JobsDB"],
};

const MATCH_META: Record<string, { label: string; mark: string }> = {
  green: { label: "高度匹配", mark: "🟢" },
  yellow: { label: "基本匹配", mark: "🟡" },
  orange: { label: "可以尝试", mark: "🟠" },
};
const MATCH_ORDER = ["green", "yellow", "orange"];

function isPdfFile(file: File) {
  return file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
}

function splitList(value: string): string[] {
  return value
    .split(/[,，、\n]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function csvCell(value: unknown): string {
  return `"${String(value ?? "").replace(/"/g, '""')}"`;
}

export function JobHuntPage() {
  const { settings } = useModelSettings();
  const featureGuard = useCareerFeatureGuard(settings, "岗位搜索");
  const [mode, setMode] = useState<JobHuntMode>("pdf");
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [backgroundText, setBackgroundText] = useState("");
  const [targetRole, setTargetRole] = useState("");
  const [targetJd, setTargetJd] = useState("");
  const [regions, setRegions] = useState<string[]>([]);
  const [citiesText, setCitiesText] = useState("");
  const [salaryRange, setSalaryRange] = useState("");
  const [requirements, setRequirements] = useState<string[]>([]);
  const [customRequirement, setCustomRequirement] = useState("");
  const [platforms, setPlatforms] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const [isDragOver, setIsDragOver] = useState(false);
  const [uploadHint, setUploadHint] = useState("");
  const [formError, setFormError] = useState("");
  const [report, setReport] = useState<ReportState>({ kind: "idle" });
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const availablePlatforms = useMemo(() => {
    const platformSet = new Set(GLOBAL_PLATFORM_OPTIONS);
    regions.forEach((region) => {
      (REGION_PLATFORM_OPTIONS[region] || []).forEach((platform) => platformSet.add(platform));
    });
    return Array.from(platformSet);
  }, [regions]);

  useEffect(() => {
    setPlatforms((current) => current.filter((platform) => availablePlatforms.includes(platform)));
  }, [availablePlatforms]);

  const toggleChip = (list: string[], setList: (value: string[]) => void, value: string) => {
    if (list.includes(value)) {
      setList(list.filter((item) => item !== value));
    } else {
      setList([...list, value]);
    }
  };

  const selectResumeFile = (file: File | null) => {
    if (!file) return;
    if (!isPdfFile(file)) {
      setUploadHint("仅支持 PDF 文件。");
      setResumeFile(null);
      return;
    }
    setUploadHint("");
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

  const groupedJobs = useMemo<Record<string, TopJob[]>>(() => {
    const groups: Record<string, TopJob[]> = { green: [], yellow: [], orange: [] };
    if (report.kind === "report" && Array.isArray(report.result.top_jobs)) {
      for (const job of report.result.top_jobs) {
        const level = MATCH_ORDER.includes(job.match_level || "") ? job.match_level! : "orange";
        groups[level].push(job);
      }
    }
    return groups;
  }, [report]);

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!targetRole.trim()) {
      setFormError("请填写岗位方向。");
      return;
    }
    if (mode === "pdf" && !resumeFile) {
      setFormError("已有简历模式请先上传 PDF 简历，或切换到没有简历模式。");
      return;
    }
    setFormError("");
    setLoading(true);
    setReport({ kind: "idle" });

    const payload = {
      target_role: targetRole,
      target_jd: targetJd,
      work_experience: backgroundText,
      target_regions: regions,
      target_cities: splitList(citiesText),
      salary_range: salaryRange,
      hard_requirements: requirements,
      platforms,
    };

    try {
      const resp =
        mode === "pdf" && resumeFile
          ? await callCareerforgeSkillMultipart<JobHuntResult>(settings, "/careerforge/job-hunt", payload, { resume: resumeFile })
          : await callCareerforgeSkill<JobHuntResult>(settings, "/careerforge/job-hunt", { ...payload, resume_text: backgroundText });
      const result = (resp.result ?? resp) as JobHuntResult;
      const jobs = Array.isArray(result?.top_jobs) ? result.top_jobs : [];
      if (!jobs.length && !result?.summary) {
        const message =
          String((resp as Record<string, unknown>).message || (resp as Record<string, unknown>).error || "") ||
          "搜索失败，请检查模型配置后重试。";
        setReport({ kind: "error", message });
      } else {
        setReport({ kind: "report", result });
      }
    } catch (error) {
      setReport({ kind: "error", message: (error as Error).message || "搜索失败，请稍后重试。" });
    } finally {
      setLoading(false);
    }
  };

  const exportCsv = () => {
    if (report.kind !== "report") return;
    const jobs = report.result.top_jobs ?? [];
    if (!jobs.length) return;
    const header = ["编号", "匹配度", "岗位名称", "公司", "城市", "薪资", "经验要求", "匹配点", "签证/工签", "标签", "来源平台", "链接", "备注"];
    const rows = jobs.map((job, index) => {
      const meta = MATCH_META[job.match_level || ""] || MATCH_META.orange;
      return [
        index + 1,
        `${meta.mark}${meta.label}`,
        job.title,
        job.company,
        job.location,
        job.salary,
        "",
        job.match_reason,
        "",
        "",
        "",
        job.url,
        "",
      ];
    });
    const csv = "\uFEFF" + [header, ...rows].map((row) => row.map(csvCell).join(",")).join("\r\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    const now = new Date();
    const date = `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, "0")}${String(now.getDate()).padStart(2, "0")}`;
    link.download = `岗位搜索结果_${date}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };

  if (report.kind === "report") {
    const { result } = report;
    return (
      <>
        {featureGuard.overlay}
        <section className="job-hunt-page">
          <header className="job-hunt-report-head">
            <div>
              <p className="job-hunt-kicker">搜索结果</p>
              <h2>值得投递的岗位</h2>
            </div>
            <div className="job-hunt-report-actions">
              <button type="button" className="ghost-btn" onClick={() => setReport({ kind: "idle" })}>
                返回修改
              </button>
              <button type="button" className="primary-btn" onClick={exportCsv} disabled={!groupedJobs.green.length && !groupedJobs.yellow.length && !groupedJobs.orange.length}>
                导出 CSV
              </button>
            </div>
          </header>

          {result.summary ? <p className="job-hunt-summary">{result.summary}</p> : null}

          {Array.isArray(result.search_strategy) && result.search_strategy.length > 0 ? (
            <section className="surface job-hunt-strategy">
              <h3>搜索策略</h3>
              <ul>
                {result.search_strategy.map((item, index) => (
                  <li key={index}>{item}</li>
                ))}
              </ul>
            </section>
          ) : null}

          {MATCH_ORDER.map((level) => {
            const jobs = groupedJobs[level];
            if (!jobs.length) return null;
            const meta = MATCH_META[level];
            return (
              <section key={level} className={`surface job-hunt-group job-hunt-group--${level}`}>
                <h3>
                  <span className="job-hunt-level-mark" aria-hidden="true">{meta.mark}</span>
                  {meta.label}
                  <span className="job-hunt-count">{jobs.length}</span>
                </h3>
                <ul className="job-hunt-list">
                  {jobs.map((job, index) => (
                    <li key={index} className="job-hunt-item">
                      <div className="job-hunt-item-main">
                        {job.url ? (
                          <a href={job.url} target="_blank" rel="noopener noreferrer" className="job-hunt-title">
                            {job.title || "未命名岗位"}
                          </a>
                        ) : (
                          <span className="job-hunt-title">{job.title || "未命名岗位"}</span>
                        )}
                        <div className="job-hunt-meta">
                          {job.company ? <span>{job.company}</span> : null}
                          {job.location ? <span>{job.location}</span> : null}
                          {job.salary ? <span className="job-hunt-salary">{job.salary}</span> : null}
                        </div>
                      </div>
                      {job.match_reason ? <p className="job-hunt-reason">{job.match_reason}</p> : null}
                    </li>
                  ))}
                </ul>
              </section>
            );
          })}

          {Array.isArray(result.next_actions) && result.next_actions.length > 0 ? (
            <section className="surface job-hunt-next">
              <h3>下一步建议</h3>
              <ul>
                {result.next_actions.map((item, index) => (
                  <li key={index}>{item}</li>
                ))}
              </ul>
            </section>
          ) : null}

          {Array.isArray(result.assumptions) && result.assumptions.length > 0 ? (
            <p className="job-hunt-assumptions">假设说明：{result.assumptions.join("；")}</p>
          ) : null}
        </section>
      </>
    );
  }

  return (
    <>
      {featureGuard.overlay}
      <section className="job-hunt-page">
        <div className="job-hunt-layout">
          <form className="surface job-hunt-form" onSubmit={onSubmit}>
            <header className="job-hunt-head">
              <div>
                <p className="job-hunt-kicker">岗位搜索</p>
                <h2>AI 岗位猎手</h2>
              </div>
            </header>
            <p className="job-hunt-guide">填写简历与搜索条件，AI 会按匹配度整理出值得投递的岗位清单。</p>

            <div className="job-hunt-mode-switch" role="group" aria-label="简历来源">
              <button type="button" className={mode === "pdf" ? "is-active" : ""} aria-pressed={mode === "pdf"} onClick={() => { setMode("pdf"); setFormError(""); }}>
                已有简历
              </button>
              <button type="button" className={mode === "conversation" ? "is-active" : ""} aria-pressed={mode === "conversation"} onClick={() => { setMode("conversation"); setFormError(""); }}>
                没有简历
              </button>
            </div>

            <div className="job-hunt-fields-grid">
              {mode === "pdf" ? (
                <div className="job-hunt-upload-wrap">
                  <div
                    className={`job-hunt-upload${isDragOver ? " is-dragover" : ""}${resumeFile ? " has-file" : ""}`}
                    role="button"
                    tabIndex={0}
                    aria-label="上传 PDF 简历"
                    onClick={() => fileInputRef.current?.click()}
                    onKeyDown={onDropzoneKeyDown}
                    onDragOver={(event) => { event.preventDefault(); setIsDragOver(true); }}
                    onDragLeave={() => setIsDragOver(false)}
                    onDrop={onDropResume}
                  >
                    <input ref={fileInputRef} className="job-hunt-file-input" type="file" accept=".pdf,application/pdf" onChange={onFileChange} />
                    <strong>{resumeFile ? "简历文件已就绪" : "上传简历文件"}</strong>
                    <span>{resumeFile ? resumeFile.name : "点击选择或拖拽 PDF 到此处"}</span>
                  </div>
                  {resumeFile ? (
                    <button type="button" className="job-hunt-file-clear" onClick={() => { setResumeFile(null); setUploadHint(""); }}>
                      移除当前文件
                    </button>
                  ) : null}
                  {uploadHint ? <p className="job-hunt-field-error" role="alert">{uploadHint}</p> : null}
                </div>
              ) : (
                <label className="job-hunt-field job-hunt-field--wide">
                  <span>背景 / 经历 <small>把你最相关的经历、技能写下来</small></span>
                  <textarea rows={3} value={backgroundText} onChange={(event) => setBackgroundText(event.target.value)} placeholder="例如：5 年前端开发，主导过组件库建设，熟悉 React 与 TypeScript…" />
                </label>
              )}

              <label className="job-hunt-field">
                <span>岗位方向 <em>必填</em></span>
                <input value={targetRole} onChange={(event) => setTargetRole(event.target.value)} placeholder="例如：数据分析师 / 前端工程师" />
              </label>

              <label className="job-hunt-field">
                <span>岗位 JD <small>可选</small></span>
                <textarea rows={3} value={targetJd} onChange={(event) => setTargetJd(event.target.value)} placeholder="粘贴目标岗位描述，帮助 AI 更精准匹配" />
              </label>

              <fieldset className="job-hunt-choice job-hunt-choice--wide">
                <legend>目标地区 <small>可多选</small></legend>
                <div className="job-hunt-chips">
                  {REGION_OPTIONS.map((option) => (
                    <button
                      key={option}
                      type="button"
                      className={regions.includes(option) ? "is-active" : ""}
                      aria-pressed={regions.includes(option)}
                      onClick={() => toggleChip(regions, setRegions, option)}
                    >
                      {option}
                    </button>
                  ))}
                </div>
              </fieldset>

              <label className="job-hunt-field">
                <span>目标城市 <small>可多填，用逗号分隔</small></span>
                <input value={citiesText} onChange={(event) => setCitiesText(event.target.value)} placeholder="例如：上海, 北京, 深圳" />
              </label>

              <label className="job-hunt-field">
                <span>期望薪资 <small>可选</small></span>
                <input value={salaryRange} onChange={(event) => setSalaryRange(event.target.value)} placeholder="例如：30-50K / 80-120 万" />
              </label>

              <fieldset className="job-hunt-choice">
                <legend>硬性要求 <small>可多选</small></legend>
                <div className="job-hunt-chips">
                  {REQUIREMENT_OPTIONS.map((option) => (
                    <button
                      key={option}
                      type="button"
                      className={requirements.includes(option) ? "is-active" : ""}
                      aria-pressed={requirements.includes(option)}
                      onClick={() => toggleChip(requirements, setRequirements, option)}
                    >
                      {option}
                    </button>
                  ))}
                  <span className="job-hunt-chip-add">
                    <input
                      value={customRequirement}
                      onChange={(event) => setCustomRequirement(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter") {
                          event.preventDefault();
                          const value = customRequirement.trim();
                          if (value && !requirements.includes(value)) {
                            setRequirements([...requirements, value]);
                            setCustomRequirement("");
                          }
                        }
                      }}
                      placeholder="自定义要求 + 回车"
                      aria-label="自定义硬性要求"
                    />
                  </span>
                </div>
              </fieldset>

              <fieldset className="job-hunt-choice">
                <legend>搜索平台 <small>可多选</small></legend>
                <p className="job-hunt-platform-hint">
                  {regions.length ? `已按 ${regions.join("、")} 推荐` : "选择国家后会补充当地常用平台"}
                </p>
                <div className="job-hunt-chips">
                  {availablePlatforms.map((option) => (
                    <button
                      key={option}
                      type="button"
                      className={platforms.includes(option) ? "is-active" : ""}
                      aria-pressed={platforms.includes(option)}
                      onClick={() => toggleChip(platforms, setPlatforms, option)}
                    >
                      {option}
                    </button>
                  ))}
                </div>
              </fieldset>
            </div>

            {formError ? <p className="job-hunt-field-error" role="alert">{formError}</p> : null}

            <button type="submit" className="primary-btn job-hunt-submit" disabled={loading}>
              {loading ? "正在搜索岗位…" : "开始搜索"}
            </button>
          </form>

          {report.kind === "error" ? (
            <div className="surface job-hunt-error" role="alert">
              <h3>搜索失败</h3>
              <p>{report.message}</p>
            </div>
          ) : null}
        </div>
      </section>
    </>
  );
}
