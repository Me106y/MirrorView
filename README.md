# MirrorView

MirrorView is an AI career training website for job seekers. It helps users prepare resumes, analyze a target role, practice interviews, and create application messages through a single web interface.

[English](README.md) | [中文](README_CN.md)

## Use It Through the Website

1. Open a deployed MirrorView site.
2. In Model Settings, choose a model provider, enter the API key, base URL, and model name, then test and save the connection.
3. Choose a tool from the home page and provide the requested resume, job description, or experience details.
4. Review the generated analysis, resume, application letter, or interview conversation. Supported tools can export HTML or PDF files.

The model API key is stored in the browser and used for model requests. Use a temporary or usage-limited key and revoke it when it is no longer needed. GitHub login is optional and depends on the deployment configuration.

<!-- Screenshot placeholder: home page and model settings. -->

## Features

### Resume Match

Upload a PDF resume and provide a target role and job description to receive:

- an overall fit assessment;
- strengths, gaps, and missing requirements mapped to the role;
- targeted resume improvement suggestions;
- an analysis report that can be viewed and exported in the site.

<!-- Screenshot placeholder: resume match results. -->

### AI Resume Craft

Complete a guided flow covering the target role, personal information, education, work or project experience, skills, and certificates. The generated resume supports:

- multiple resume templates;
- Chinese, English, or bilingual output;
- an optional profile photo;
- HTML and PDF preview/export.

<!-- Screenshot placeholder: resume form and preview. -->

### Cover Letter

Provide a company, job description, and resume content to generate a tailored application message. Email and recruitment-platform chat scenarios are currently supported.

<!-- Screenshot placeholder: cover letter page. -->

### Text Mock Interview

Start with a target role or an answer, then continue the conversation with the AI interviewer. The interviewer uses the conversation context for follow-up questions and is suitable for practicing:

- introductions and motivation;
- project and behavioral questions;
- technical, business, and situational answers;
- answer structure and interview communication.

### Job Search

The job search entry is present in the navigation, but this version is still a placeholder. Live job data sources and the complete asynchronous search workflow are planned for a later phase.

## Run Locally

This section is for self-hosting and development. Regular users only need access to a deployed website.

### Requirements

- Python 3.11+
- Node.js 20+
- npm 10+

### Install

The project keeps one Python dependency file and one environment template:

```bash
pip install -r requirements.txt
cd web
npm install
cd ..
```

Copy the environment template and configure a model provider:

```bash
cp .env.example .env
```

At least one model API key is required. The default example uses DeepSeek:

```dotenv
PLATFORM_PROVIDER=deepseek
PLATFORM_MODEL=deepseek-chat
DEEPSEEK_API_KEY=sk-...
```

Never commit real credentials.

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

## Project Status

The currently usable tools are Resume Match, AI Resume Craft, Cover Letter, and Text Mock Interview. Job Search is reserved for a future iteration.

## License

MIT License. See `LICENSE` for details.
