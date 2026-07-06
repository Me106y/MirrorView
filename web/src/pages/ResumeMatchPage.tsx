import { FormEvent, useState } from "react";
import { callCareerforgeSkill } from "../lib/api";
import { useModelSettings } from "../context/ModelSettingsContext";

export function ResumeMatchPage() {
  const { settings } = useModelSettings();
  const [resumeText, setResumeText] = useState("");
  const [jdText, setJdText] = useState("");
  const [targetRole, setTargetRole] = useState("");
  const [output, setOutput] = useState<string>("");
  const [loading, setLoading] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      const resp = await callCareerforgeSkill(settings, "/careerforge/resume-match", {
        resume_text: resumeText,
        jd_text: jdText,
        target_role: targetRole
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
        <h2>Resume Match</h2>
        <label>目标岗位</label>
        <input value={targetRole} onChange={(e) => setTargetRole(e.target.value)} />
        <label>简历文本</label>
        <textarea rows={8} value={resumeText} onChange={(e) => setResumeText(e.target.value)} />
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
