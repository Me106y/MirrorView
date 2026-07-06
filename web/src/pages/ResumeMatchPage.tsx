import { FormEvent, useState } from "react";
import { callCareerforgeSkillMultipart } from "../lib/api";
import { useModelSettings } from "../context/ModelSettingsContext";

export function ResumeMatchPage() {
  const { settings } = useModelSettings();
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [jdText, setJdText] = useState("");
  const [targetRole, setTargetRole] = useState("");
  const [output, setOutput] = useState<string>("");
  const [loading, setLoading] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!resumeFile) {
      setOutput("请先上传 PDF 简历文件。");
      return;
    }

    if (!resumeFile.name.toLowerCase().endsWith(".pdf")) {
      setOutput("仅支持 PDF 文件。");
      return;
    }

    setLoading(true);
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
      setOutput(JSON.stringify(resp.result ?? resp, null, 2));
    } catch (err) {
      setOutput((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <section className="card-grid">
      <form className="surface" onSubmit={onSubmit}>
        <h2>Resume Match</h2>
        <label>目标岗位</label>
        <input value={targetRole} onChange={(e) => setTargetRole(e.target.value)} />
        <label>上传简历（仅支持 PDF）</label>
        <input
          type="file"
          accept=".pdf,application/pdf"
          onChange={(e) => setResumeFile(e.target.files?.[0] ?? null)}
        />
        {resumeFile ? <p className="muted">已选择：{resumeFile.name}</p> : null}
        <label>岗位 JD</label>
        <textarea rows={8} value={jdText} onChange={(e) => setJdText(e.target.value)} />
        <button className="primary-btn" disabled={loading}>
          {loading ? "分析中..." : "生成匹配分析"}
        </button>
      </form>
      <article className="surface output-panel">
        <h3>结果</h3>
        <pre>{output || "提交后将在这里显示 JSON 结果"}</pre>
      </article>
    </section>
  );
}
