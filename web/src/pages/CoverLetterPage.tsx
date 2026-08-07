import { FormEvent, useState } from "react";
import { NavLink } from "react-router-dom";
import { callCareerforgeSkill } from "../lib/api";
import { useModelSettings } from "../context/ModelSettingsContext";
import { useCareerFeatureGuard } from "../components/CareerFeatureGuard";

export function CoverLetterPage() {
  const { settings } = useModelSettings();
  const featureGuard = useCareerFeatureGuard(settings, "求职信生成");
  const [resumeText, setResumeText] = useState("");
  const [jdText, setJdText] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [scenario, setScenario] = useState("email");
  const [output, setOutput] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [copyState, setCopyState] = useState<"idle" | "copied" | "error">("idle");

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setCopyState("idle");
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

  const onCopyOutput = async () => {
    if (!output) return;

    try {
      await navigator.clipboard.writeText(output);
      setCopyState("copied");
    } catch {
      setCopyState("error");
    }
  };

  const copyLabel = copyState === "copied" ? "已复制" : copyState === "error" ? "复制失败" : "复制结果";

  return (
    <>
      {featureGuard.overlay}
    <section className="cover-letter-page">
      <NavLink to="/" className="back-home-btn">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M19 12H5M12 19l-7-7 7-7"/>
        </svg>
        返回
      </NavLink>
      <div className="card-grid cover-letter-layout">
        <form className="surface" onSubmit={onSubmit}>
          <h2>求职信撰写</h2>
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
          <div className="cover-letter-output-head">
            <h3>结果</h3>
            <button
              type="button"
              className="cover-letter-output-copy-btn"
              onClick={() => void onCopyOutput()}
              disabled={!output}
              aria-label={copyLabel}
              title={copyLabel}
            >
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <rect x="9" y="9" width="11" height="11" rx="2" />
                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
              </svg>
            </button>
          </div>
          <pre>{output || "提交后将在这里显示 JSON 结果"}</pre>
        </article>
      </div>
    </section>
    </>
  );
}
