import { NavLink } from "react-router-dom";

const ENTRIES = [
  {
    to: "/resume-match",
    title: "简历分析匹配",
    desc: "智能分析简历与目标岗位的匹配度，提供针对性优化建议。",
    icon: "RM"
  },
  {
    to: "/resume-craft",
    title: "简历生成",
    desc: "AI 辅助生成专业简历，根据行业特点定制最佳模板。",
    icon: "RC"
  },
  {
    to: "/cover-letter",
    title: "求职信撰写",
    desc: "智能撰写个性化求职信，突出个人优势与岗位契合度。",
    icon: "CL"
  },
  {
    to: "/mock-interview",
    title: "模拟面试",
    desc: "AI 模拟真实面试场景，提供即时反馈与改进建议。",
    icon: "MI"
  },
  {
    to: "/job-hunt",
    title: "岗位搜索",
    desc: "智能发现匹配职位，精准推荐符合您技能的机会。",
    icon: "JH"
  }
];

export function HomePage() {
  return (
    <section className="home-landing">
      <header className="home-landing-hero">
        <span className="home-landing-badge">AI 驱动的求职训练平台</span>
        <h2>智能求职助手</h2>
        <p>
          利用人工智能技术，为您的求职之路提供全方位支持。
          <br />
          从简历优化到模拟面试，让每一次投递更有把握。
        </p>
      </header>

      <div className="home-landing-grid">
        {ENTRIES.map((item) => (
          <NavLink key={item.to} to={item.to} className="landing-card">
            <span className="landing-card-icon">{item.icon}</span>
            <h3>{item.title}</h3>
            <p>{item.desc}</p>
            <span className="landing-card-cta">开始使用</span>
          </NavLink>
        ))}
        <article className="landing-card landing-card-placeholder">
          <span className="landing-card-icon">+</span>
          <h3>更多功能</h3>
          <p>敬请期待</p>
        </article>
      </div>

      <p className="home-landing-footnote">智能求职训练平台 · 让求职更高效</p>
    </section>
  );
}
