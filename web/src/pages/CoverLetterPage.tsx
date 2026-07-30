import { FormEvent, useState } from "react";
import { NavLink } from "react-router-dom";
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
      <NavLink to="/" className="back-home-btn">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M19 12H5M12 19l-7-7 7-7"/>
        </svg>
        返回首页
      </NavLink>
      <form className="surface" onSubmit={onSubmit}>
        <h2>Cover Letter</h2>
        <label htmlFor="cl-company">公司名</label>
        <input id="cl-company" value={companyName} onChange={(e) => setCompanyName(e.target.value)} />
        <label htmlFor="cl-scenario">场景</label>
        <select id="cl-scenario" value={scenario} onChange={(e) => setScenario(e.target.value)}>
          <option value="email">email</option>
          <option value="chat">chat</option>
        </select>
        <label htmlFor="cl-resume">简历文本</label>
        <textarea id="cl-resume" rows={8} value={resumeText} onChange={(e) => setResumeText(e.target.value)} />
        <label htmlFor="cl-jd">岗位 JD</label>
        <textarea id="cl-jd" rows={8} value={jdText} onChange={(e) => setJdText(e.target.value)} />
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
