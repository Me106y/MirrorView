# MirrorView 🪞

<div align="center">

[![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.1-000000?style=for-the-badge&logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![React](https://img.shields.io/badge/React-18-20232A?style=for-the-badge&logo=react&logoColor=61DAFB)](https://react.dev/)
[![Vercel](https://img.shields.io/badge/Vercel-Production-000000?style=for-the-badge&logo=vercel&logoColor=white)](https://vercel.com/)

[English](README.md) | [中文](README_CN.md)

</div>

MirrorView 是一个面向求职者的 AI 求职工具网站，帮助用户完成从简历准备到面试练习的核心工作。网站采用 React + Vite 构建前端，Flask 提供后端接口，AI 能力由 CareerForge 工作流驱动，并支持部署到 Vercel。

## 通过网站使用

1. 打开已部署的 MirrorView 网站。
2. 在“模型设置”中填写 DeepSeek API Key、Base URL 和模型名称，测试连接并保存。
3. 从首页选择需要的求职工具，按页面提示输入简历、岗位 JD 或个人信息。
4. 查看 AI 生成的分析、对话或文案结果，并在支持的页面导出 HTML / PDF。

模型 API Key 由浏览器端保存并用于请求模型。请使用临时或额度受限的 Key，并在不再使用时及时撤销。

<!-- 截图占位：此处可补充首页、模型设置和主要功能页面截图。 -->

## 网站功能

### 简历匹配分析

上传 PDF 简历并填写目标岗位和岗位 JD，获取匹配度分析、优势与差距、针对性的简历优化建议，以及可继续使用的结果报告。

### AI 简历生成

通过五步工作流逐步完善目标岗位、个人信息、教育背景、经历和项目内容。支持选择简历模板、中文 / 英文 / 中英文双版、可选证件照，并预览和导出 HTML / PDF 简历。

### 求职信撰写

输入公司、岗位 JD 和简历内容，生成针对具体投递场景的个性化求职信。目前支持邮件和聊天两种场景。

### 文字模拟面试

以对话方式进行 AI 面试练习。用户可以说明目标岗位并持续回答问题，系统会根据上下文进行多轮追问，适合用于面试表达和回答思路训练。

### 岗位搜索

岗位搜索页面已保留在网站导航中，目前处于功能占位阶段，后续再接入职位数据源和异步搜索流程。

## 本地运行

### 环境要求

- Python 3.11+
- Node.js 20+
- npm 10+

### 安装

```bash
pip install -r requirements.txt
cd web
npm install
cd ..
```

### 配置环境变量

复制唯一的环境变量模板，并填写本地需要的配置：

```bash
cp .env.example .env
```

至少配置一个模型 API Key。默认配置使用 DeepSeek：

```dotenv
PLATFORM_PROVIDER=deepseek
PLATFORM_MODEL=deepseek-chat
DEEPSEEK_API_KEY=sk-...
```

`.env.example` 同时列出了 OpenAI、Anthropic、GitHub OAuth、Session 和 Turnstile 等可选配置。真实密钥不要提交到 Git。

### 启动服务

在仓库根目录启动后端：

```bash
python -m server.app
```

另开一个终端启动前端：

```bash
cd web
npm run dev
```

默认地址：

- 网站前端：`http://localhost:5173`
- Flask API：`http://localhost:5001`

## 部署

项目已按 Vercel 部署结构组织：

- `web/` 构建前端静态资源
- `api/index.py` 作为 Python Function 入口
- `server/` 保存后端源码
- `api/` 保存由脚本同步生成的运行时镜像
- `vercel.json` 定义构建和路由规则

部署前请在 Vercel 项目设置中配置模型 API Key 等环境变量，然后执行：

```bash
npx vercel --prod
```

修改后端运行时代码后，需要重新同步 Vercel 运行时文件：

```bash
./scripts/sync_api_runtime.sh
```

## 技术栈

- 前端：React、TypeScript、Vite
- 后端：Flask、SQLAlchemy
- AI：LangChain、DeepSeek / OpenAI 兼容模型接口
- 部署：Vercel

## 开发校验

```bash
python -m py_compile server/app.py server/routes.py server/services/*.py
cd web && npm run build
cd .. && ./scripts/sync_api_runtime.sh
```

## License

本项目采用 MIT License，详见 `LICENSE`。
