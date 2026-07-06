import { FormEvent, useState } from "react";
import { callCareerforgeSkill } from "../lib/api";
import { useModelSettings } from "../context/ModelSettingsContext";

export function CoverLetterPage() {
  const { settings } = useModelSettings();
  const [resumeText, setResumeText] = useState("");
  const [jdText, setJdText] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [scenario, setScenario] = useState("email");
  const [output, setOutput] = useState<string>("");
  const [loading, setLoading] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      const resp = await callCareerforgeSkill(settings, "/careerforge/cover-letter", {
        resume_text: resumeText,
        jd_text: jdText,
        company_name: companyName,
        scenario,
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
        <h2>Cover Letter</h2>
        <label>公司名</label>
        <input value={companyName} onChange={(e) => setCompanyName(e.target.value)} />
        <label>场景</label>
        <select value={scenario} onChange={(e) => setScenario(e.target.value)}>
          <option value="email">email</option>
          <option value="chat">chat</option>
        </select>
        <label>简历文本</label>
        <textarea rows={8} value={resumeText} onChange={(e) => setResumeText(e.target.value)} />
        <label>岗位 JD</label>
        <textarea rows={8} value={jdText} onChange={(e) => setJdText(e.target.value)} />
        <button className="primary-btn" disabled={loading}>
          {loading ? "生成中..." : "生成求职信"}
        </button>
      </form>
      <article className="surface output-panel">
        <h3>结果</h3>
        <pre>{output || "提交后将在这里显示 JSON 结果"}</pre>
      </article>
    </section>
  );
}
