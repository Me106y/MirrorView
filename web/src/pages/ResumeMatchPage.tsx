import { DragEvent, FormEvent, KeyboardEvent, useMemo, useRef, useState } from "react";
import { callCareerforgeSkillMultipart } from "../lib/api";
import { useModelSettings } from "../context/ModelSettingsContext";

type ResultState = {
  kind: "idle" | "report" | "error";
  text: string;
};

function isPdfFile(file: File) {
  const byName = file.name.toLowerCase().endsWith(".pdf");
  const byType = file.type === "application/pdf";
  return byName || byType;
}

function highlightJson(text: string) {
  const escaped = text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  return escaped
    .replace(/"([^"\\]*(?:\\.[^"\\]*)*)"(?=\s*:)/g, '<span class="json-key">"$1"</span>')
    .replace(/:\s*"([^"\\]*(?:\\.[^"\\]*)*)"/g, ': <span class="json-string">"$1"</span>')
    .replace(/\b(true|false|null)\b/g, '<span class="json-literal">$1</span>')
    .replace(/(-?\b\d+(?:\.\d+)?\b)/g, '<span class="json-number">$1</span>');
}

export function ResumeMatchPage() {
  const { settings } = useModelSettings();
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [jdText, setJdText] = useState("");
  const [targetRole, setTargetRole] = useState("");
  const [result, setResult] = useState<ResultState>({ kind: "idle", text: "" });
  const [uploadHint, setUploadHint] = useState("");
  const [resultNotice, setResultNotice] = useState("");
  const [isDragOver, setIsDragOver] = useState(false);
  const [loading, setLoading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const canSubmit = Boolean(targetRole.trim() && jdText.trim() && resumeFile) && !loading;

  const highlightedResult = useMemo(() => {
    if (result.kind !== "report") {
      return "";
    }
    return highlightJson(result.text);
  }, [result]);

  const setResume = (file: File | null) => {
    if (!file) {
      setResumeFile(null);
      setUploadHint("");
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
      return;
    }
    if (!isPdfFile(file)) {
      setResumeFile(null);
      setUploadHint("仅支持 PDF 文件。");
      return;
    }
    setResumeFile(file);
    setUploadHint("");
  };

  const onDropResume = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragOver(false);
    const file = e.dataTransfer.files?.[0] ?? null;
    setResume(file);
  };

  const onDropzoneKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      fileInputRef.current?.click();
    }
  };

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!resumeFile) {
      setResult({ kind: "error", text: "请先上传 PDF 简历文件。" });
      return;
    }

    if (!isPdfFile(resumeFile)) {
      setResult({ kind: "error", text: "仅支持 PDF 文件。" });
      return;
    }

    setLoading(true);
    setResultNotice("");
    try {
      const resp = await callCareerforgeSkillMultipart(
        settings,
        "/careerforge/resume-match",
        {
          jd_text: jdText,
          target_role: targetRole
        },
        {
          resume: resumeFile
        }
      );
      setResult({ kind: "report", text: JSON.stringify(resp.result ?? resp, null, 2) });
    } catch (err) {
      setResult({ kind: "error", text: (err as Error).message });
    } finally {
      setLoading(false);
    }
  };

  const copyReport = async () => {
    if (!result.text) {
      return;
    }
    try {
      await navigator.clipboard.writeText(result.text);
      setResultNotice("已复制到剪贴板");
    } catch {
      setResultNotice("复制失败，请手动复制");
    }
  };

  const exportReport = () => {
    if (!result.text) {
      return;
    }
    const blob = new Blob([result.text], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "resume-match-report.txt";
    link.click();
    URL.revokeObjectURL(url);
    setResultNotice("已导出文本");
  };

  return (
    <section className="resume-match-page">
      <div className="resume-match-layout">
        <form className="surface resume-match-form" onSubmit={onSubmit}>
          <header className="resume-match-form-head">
            <h2>Resume Match</h2>
            <p>上传简历与岗位 JD，AI 自动计算匹配度并给出优化建议。</p>
          </header>

          <label>目标岗位</label>
          <input value={targetRole} onChange={(e) => setTargetRole(e.target.value)} placeholder="例如：AI 产品经理" />

          <label>上传简历（仅支持 PDF）</label>
          <div
            className={`resume-dropzone${isDragOver ? " is-dragover" : ""}${resumeFile ? " has-file" : ""}`}
            role="button"
            tabIndex={0}
            aria-label="上传 PDF 简历"
            onClick={() => fileInputRef.current?.click()}
            onKeyDown={onDropzoneKeyDown}
            onDragOver={(e) => {
              e.preventDefault();
              setIsDragOver(true);
            }}
            onDragLeave={() => setIsDragOver(false)}
            onDrop={onDropResume}
          >
            <input
              ref={fileInputRef}
              className="resume-file-input"
              type="file"
              accept=".pdf,application/pdf"
              onChange={(e) => setResume(e.target.files?.[0] ?? null)}
            />
            <span className="resume-dropzone-icon" aria-hidden="true">
              ↑
            </span>
            <p className="resume-dropzone-title">
              {resumeFile ? "PDF 简历已上传" : "点击或拖拽 PDF 简历到此处上传"}
            </p>
            <p className="resume-dropzone-sub">{resumeFile ? resumeFile.name : "仅支持 .pdf 文件"}</p>
            {resumeFile ? (
              <button
                type="button"
                className="resume-file-clear"
                onClick={(e) => {
                  e.stopPropagation();
                  setResume(null);
                }}
              >
                删除文件
              </button>
            ) : null}
          </div>

          {uploadHint ? <p className="resume-form-error">{uploadHint}</p> : null}
          {!uploadHint && resumeFile ? <p className="resume-file-ok">✓ PDF 文件就绪</p> : null}

          <label>岗位 JD</label>
          <textarea
            rows={10}
            value={jdText}
            onChange={(e) => setJdText(e.target.value)}
            placeholder="粘贴岗位描述，建议包含职责、要求与加分项"
          />

          <button className="primary-btn resume-submit-btn" disabled={!canSubmit}>
            <span aria-hidden="true">◍</span>
            {loading ? "分析中..." : "AI 生成匹配分析"}
          </button>
          {!canSubmit && !loading ? <p className="resume-form-tip">请填写完整信息后提交分析。</p> : null}
        </form>

        <article className="surface resume-match-result">
          <header className="resume-result-head">
            <h3>结果</h3>
            <span>AI 匹配分析报告</span>
          </header>

          <div className={`resume-result-body${result.kind === "idle" ? " is-empty" : ""}`}>
            {result.kind === "idle" ? (
              <div className="resume-result-empty">
                <span className="resume-result-empty-icon">◌</span>
                <p>填写左侧信息并提交，匹配分析结果将在此展示。</p>
              </div>
            ) : null}
            {result.kind === "error" ? <p className="resume-result-error">{result.text}</p> : null}
            {result.kind === "report" ? (
              <pre className="resume-json-view">
                <code dangerouslySetInnerHTML={{ __html: highlightedResult }} />
              </pre>
            ) : null}
          </div>

          <div className="resume-result-actions">
            <button type="button" className="ghost-btn" onClick={copyReport} disabled={!result.text}>
              复制报告
            </button>
            <button type="button" className="ghost-btn" onClick={exportReport} disabled={!result.text}>
              导出文本
            </button>
          </div>
          {resultNotice ? <p className="resume-result-note">{resultNotice}</p> : null}
        </article>
      </div>
    </section>
  );
}
