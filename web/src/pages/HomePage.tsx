import { NavLink } from "react-router-dom";

const ENTRIES = [
  {
    to: "/resume-match",
    title: "Resume Match",
    desc: "分析简历与 JD 的匹配度并输出差距建议。"
  },
  {
    to: "/resume-craft",
    title: "Resume Craft",
    desc: "根据目标岗位生成或优化简历内容。"
  },
  {
    to: "/cover-letter",
    title: "Cover Letter",
    desc: "基于简历与岗位 JD 生成定制化求职信。"
  },
  {
    to: "/mock-interview",
    title: "Mock Interview",
    desc: "进行对话式模拟面试并获得即时反馈。"
  },
  {
    to: "/job-hunt",
    title: "Job Hunt",
    desc: "查看岗位搜索入口与后续能力规划。"
  }
];

export function HomePage() {
  return (
    <section className="home-hub surface">
      <header className="home-hub-header">
        <h2>MirrorView 功能入口</h2>
        <p>选择一个卡片开始使用对应功能。</p>
      </header>
      <div className="home-hub-grid">
        {ENTRIES.map((item) => (
          <NavLink key={item.to} to={item.to} className="home-card">
            <h3>{item.title}</h3>
            <p>{item.desc}</p>
            <span>进入页面</span>
          </NavLink>
        ))}
      </div>
    </section>
  );
}
