# MirrorView 🪞

<div align="center">

[![Python](https://img.shields.io/badge/Python-3.11-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.1-000000?style=for-the-badge&logo=flask&logoColor=white)](https://flask.palletsprojects.com/)
[![React](https://img.shields.io/badge/React-18-20232A?style=for-the-badge&logo=react&logoColor=61DAFB)](https://react.dev/)
[![Vercel](https://img.shields.io/badge/Vercel-Production-000000?style=for-the-badge&logo=vercel&logoColor=white)](https://vercel.com/)

[English](README.md) | [中文](README_CN.md)

</div>

MirrorView is an AI career toolkit for job seekers. It helps users prepare resumes, compare a resume with a target job description, write application messages, and practice interviews through a web interface. The product uses a React + Vite frontend, a Flask API, and CareerForge workflows, and is ready for Vercel deployment.

## Use It Through the Website

1. Open a deployed MirrorView site.
2. Open Model Settings and enter a DeepSeek API key, base URL, and model name. Test and save the connection.
3. Choose a career tool from the home page and provide the requested resume, job description, or profile information.
4. Review the generated analysis, conversation, or application content. Supported pages can export HTML or PDF files.

The model API key is kept in the browser and used for model requests. Use a temporary or usage-limited key and revoke it when it is no longer needed.

<!-- Screenshot placeholder: add the home page, model settings, and feature page screenshots here. -->

## Features

### Resume Match

Upload a PDF resume and provide a target role and job description. MirrorView returns a match analysis, strengths and gaps, targeted improvement suggestions, and a reusable report.

### AI Resume Craft

Complete a five-step workflow covering the target role, personal details, education, experience, and projects. Choose a resume template, Chinese / English / bilingual output, and an optional photo, then preview and export the result as HTML or PDF.

### Cover Letter

Provide a company, job description, and resume content to generate a tailored application letter. Email and chat scenarios are currently supported.

### Text Mock Interview

Practice with an AI interviewer in a conversational interface. The assistant uses the conversation history to ask follow-up questions, making it useful for practicing interview answers and structure.

### Job Search

The job search page is present in the navigation but is currently a placeholder. Job data sources and asynchronous search workflows will be added in a later phase.

## Run Locally

### Requirements

- Python 3.11+
- Node.js 20+
- npm 10+

### Install

```bash
pip install -r requirements.txt
cd web
npm install
cd ..
```

### Configure Environment

Copy the single environment template and fill in the values needed locally:

```bash
cp .env.example .env
```

At least one model API key is required. The default configuration uses DeepSeek:

```dotenv
PLATFORM_PROVIDER=deepseek
PLATFORM_MODEL=deepseek-chat
DEEPSEEK_API_KEY=sk-...
```

`.env.example` also lists optional OpenAI, Anthropic, GitHub OAuth, session, and Turnstile settings. Never commit real credentials.

### Start the Services

Start the backend from the repository root:

```bash
python -m server.app
```

In another terminal, start the frontend:

```bash
cd web
npm run dev
```

Default URLs:

- Frontend: `http://localhost:5173`
- Flask API: `http://localhost:5001`

## Deployment

The project is structured for Vercel:

- `web/` builds the frontend assets
- `api/index.py` is the Python Function entrypoint
- `server/` contains the backend source of truth
- `api/` contains the generated runtime mirror
- `vercel.json` defines the build and routing behavior

Configure model API keys and other required environment variables in the Vercel project settings, then deploy with:

```bash
npx vercel --prod
```

After changing backend runtime code, regenerate the Vercel runtime mirror:

```bash
./scripts/sync_api_runtime.sh
```

## Tech Stack

- Frontend: React, TypeScript, Vite
- Backend: Flask, SQLAlchemy
- AI: LangChain with DeepSeek / OpenAI-compatible model APIs
- Deployment: Vercel

## Validation

```bash
python -m py_compile server/app.py server/routes.py server/services/*.py
cd web && npm run build
cd .. && ./scripts/sync_api_runtime.sh
```

## License

This project is licensed under the MIT License. See `LICENSE` for details.
