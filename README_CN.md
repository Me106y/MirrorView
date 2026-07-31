# MirrorView 🪞

<div align="center">

[![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.1-000000?style=for-the-badge&logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![React](https://img.shields.io/badge/React-18-20232A?style=for-the-badge&logo=react&logoColor=61DAFB)](https://react.dev/)
[![Vercel](https://img.shields.io/badge/Vercel-Production-000000?style=for-the-badge&logo=vercel&logoColor=white)](https://vercel.com/)

[English](README.md) | [中文](README_CN.md)

</div>

---

## 项目概述

**MirrorView** 现在是一个 **面向 Vercel 部署的 Web 应用**，核心聚焦在 CareerForge 工作流：

- `resume-match`
- `resume-craft`
- `cover-letter`
- `mock-interview`
- `job-hunt`

本次瘦身后，仓库已经移除了旧的：

- Qt 桌面端
- CLI / TUI 终端端
- Streamlit 页面

当前保留并维护的主链路是：

- `web/`：React + Vite 前端
- `server/`：Flask 后端源码
- `api/`：Vercel 运行时镜像

## 已移除内容

仓库已不再包含：

- PyQt 桌面 UI
- 终端/TUI 启动器与安装脚本
- Streamlit 应用
- Boson TTS 集成包
- Docker + Nginx 自托管部署包

`client/core/` 中仅保留少量 **纯 Python 报告生成模块**，因为后端仍会复用这些逻辑来生成 HTML 报告。

## 当前目录结构

```text
web/                 React 前端
server/              Flask 后端源码（唯一真源）
api/                 Vercel 运行时镜像
skills/              CareerForge skill 定义
scripts/sync_api_runtime.sh
vercel.json
requirements.txt
```

## 技术栈

- **前端**：React、TypeScript、Vite
- **后端**：Flask、SQLAlchemy
- **模型运行时**：DeepSeek / OpenAI 兼容接口 + LangChain
- **部署平台**：Vercel

## 本地开发

### 前置要求

- Python 3.11+
- Node.js 20+
- npm 10+

### 安装依赖

```bash
pip install -r requirements.txt
cd web
npm install
cd ..
```

### 环境变量

如有需要，可在仓库根目录创建 `.env`：

```bash
DEEPSEEK_API_KEY=sk-...
PLATFORM_PROVIDER=deepseek
PLATFORM_MODEL=deepseek-chat
```

生产环境建议直接在 Vercel 中配置环境变量。

### 本地启动

启动后端：

```bash
python -m server.app
```

启动前端：

```bash
cd web
npm run dev
```

默认本地地址：

- 前端：`http://localhost:5173`
- 后端：`http://localhost:5001`

## Vercel 部署

本仓库已经按 Vercel 方式组织完成：

- `web/` 构建前端静态资源
- `api/index.py` 作为 Python Function 入口
- `scripts/sync_api_runtime.sh` 把运行时依赖镜像到 `api/`
- `vercel.json` 定义构建、重写与路由规则

### 部署命令

在仓库根目录执行：

```bash
npx vercel --prod
```

也可以直接将 GitHub 仓库连接到 Vercel，让 `main` 分支推送自动触发生产部署。

## 主要路由

### 页面路由

- `/`
- `/resume-match`
- `/resume-craft`
- `/cover-letter`
- `/mock-interview`
- `/job-hunt`

### 法务页面

- `/legal/privacy`
- `/legal/terms`
- `/legal/ai-disclaimer`
- `/legal/byok-risk`

### 后端接口

- `/careerforge/runtime/check`
- `/careerforge/resume-match`
- `/careerforge/resume-craft`
- `/careerforge/resume-craft/chat-turn`
- `/careerforge/resume-craft/render`
- `/careerforge/cover-letter`
- `/careerforge/agent/chat`

## 开发说明

- `server/` 是后端逻辑唯一真源。
- `api/` 是通过 `scripts/sync_api_runtime.sh` 生成的 Vercel 运行时镜像。
- 修改后端运行时代码后，请重新执行：

```bash
./scripts/sync_api_runtime.sh
```

## 部署前校验

建议在部署前执行：

```bash
python -m py_compile server/app.py server/routes.py server/services/*.py
cd web && npm run build
cd .. && ./scripts/sync_api_runtime.sh
```

## License

本项目采用 MIT License，详见 `LICENSE`。
