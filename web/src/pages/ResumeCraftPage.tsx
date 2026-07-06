import { FormEvent, useState } from "react";
import { callCareerforgeSkill } from "../lib/api";
import { useModelSettings } from "../context/ModelSettingsContext";

export function ResumeCraftPage() {
  const { settings } = useModelSettings();
  const [resumeText, setResumeText] = useState("");
  const [targetRole, setTargetRole] = useState("");
  const [template, setTemplate] = useState("editorial");
  const [output, setOutput] = useState<string>("");
  const [loading, setLoading] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      const resp = await callCareerforgeSkill(settings, "/careerforge/resume-craft", {
        resume_text: resumeText,
        target_role: targetRole,
        template,
        language: "zh"
      });
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
        <h2>Resume Craft</h2>
        <label>目标岗位</label>
        <input value={targetRole} onChange={(e) => setTargetRole(e.target.value)} />
        <label>模板名</label>
        <input value={template} onChange={(e) => setTemplate(e.target.value)} />
        <label>简历文本</label>
        <textarea rows={12} value={resumeText} onChange={(e) => setResumeText(e.target.value)} />
        <button className="primary-btn" disabled={loading}>
          {loading ? "生成中..." : "生成简历"}
        </button>
      </form>
      <article className="surface output-panel">
        <h3>结果</h3>
        <pre>{output || "提交后将在这里显示 JSON 结果"}</pre>
      </article>
    </section>
  );
}
